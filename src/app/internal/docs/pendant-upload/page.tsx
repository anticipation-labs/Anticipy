"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";

// ─── Web Serial API types (minimal declarations) ──────────────────────────────
declare global {
  interface SerialPort {
    open(options: { baudRate: number }): Promise<void>;
    close(): Promise<void>;
    setSignals(signals: { dataTerminalReady?: boolean; requestToSend?: boolean }): Promise<void>;
    readonly readable: ReadableStream<Uint8Array> | null;
    readonly writable: WritableStream<Uint8Array> | null;
  }
}

// ─── ESP32 ROM Bootloader Protocol Constants ─────────────────────────────────
const ESP_ROM_BAUD = 115200;
const FLASH_BAUD = 921600;
const SYNC_CMD = 0x08;
const FLASH_BEGIN = 0x02;
const FLASH_DATA = 0x03;
const FLASH_END = 0x04;
const CHANGE_BAUDRATE = 0x0f;
const FLASH_BLOCK_SIZE = 0x4000; // 16KB blocks
const ESP_CHECKSUM_MAGIC = 0xef;

function slip_encode(data: Uint8Array): Uint8Array {
  const out: number[] = [0xc0];
  for (let i = 0; i < data.length; i++) {
    const b = data[i];
    if (b === 0xc0) { out.push(0xdb, 0xdc); }
    else if (b === 0xdb) { out.push(0xdb, 0xdd); }
    else { out.push(b); }
  }
  out.push(0xc0);
  return new Uint8Array(out);
}

function make_cmd(cmd: number, data: Uint8Array, chk = 0): Uint8Array {
  const buf = new Uint8Array(8 + data.length);
  const view = new DataView(buf.buffer);
  view.setUint8(0, 0x00);
  view.setUint8(1, cmd);
  view.setUint16(2, data.length, true);
  view.setUint32(4, chk, true);
  buf.set(data, 8);
  return slip_encode(buf);
}

function checksum(data: Uint8Array): number {
  let s = ESP_CHECKSUM_MAGIC;
  for (let i = 0; i < data.length; i++) s ^= data[i];
  return s;
}

// ─── Types ────────────────────────────────────────────────────────────────────
type Phase =
  | "idle"
  | "connecting"
  | "syncing"
  | "flashing"
  | "verifying"
  | "done"
  | "error";

interface LogEntry {
  ts: number;
  level: "info" | "ok" | "warn" | "error";
  text: string;
}

// ─── Flash engine ─────────────────────────────────────────────────────────────
class ESP32Flasher {
  private port: SerialPort;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private buf: number[] = [];

  constructor(port: SerialPort) {
    this.port = port;
  }

  async open(baud: number) {
    await this.port.open({ baudRate: baud });
    this.writer = this.port.writable!.getWriter();
    this.reader = this.port.readable!.getReader();
  }

  async close() {
    try { this.reader?.cancel(); } catch { /* ignore */ }
    try { this.reader?.releaseLock(); } catch { /* ignore */ }
    try { this.writer?.releaseLock(); } catch { /* ignore */ }
    try { await this.port.close(); } catch { /* ignore */ }
  }

  async write(data: Uint8Array) {
    await this.writer!.write(data);
  }

  async readByte(timeoutMs = 3000): Promise<number | null> {
    if (this.buf.length > 0) return this.buf.shift()!;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const p = this.reader!.read();
      const t = new Promise<null>((r) => setTimeout(() => r(null), Math.min(200, deadline - Date.now())));
      const result = await Promise.race([p, t]);
      if (!result) continue;
      const { value, done } = result as ReadableStreamReadResult<Uint8Array>;
      if (done || !value) continue;
      for (let i = 0; i < value.length; i++) this.buf.push(value[i]);
      if (this.buf.length > 0) return this.buf.shift()!;
    }
    return null;
  }

  async readSlipPacket(timeoutMs = 5000): Promise<Uint8Array | null> {
    const deadline = Date.now() + timeoutMs;
    // wait for start of packet
    while (Date.now() < deadline) {
      const b = await this.readByte(500);
      if (b === 0xc0) break;
    }
    const out: number[] = [];
    while (Date.now() < deadline) {
      const b = await this.readByte(500);
      if (b === null) return null;
      if (b === 0xc0) return new Uint8Array(out);
      if (b === 0xdb) {
        const next = await this.readByte(500);
        if (next === 0xdc) out.push(0xc0);
        else if (next === 0xdd) out.push(0xdb);
        else return null;
      } else {
        out.push(b);
      }
    }
    return null;
  }

  async toggleBootMode() {
    // Pull GPIO0 low (DTR) and pulse RESET (RTS) to enter bootloader
    await this.port.setSignals({ dataTerminalReady: false, requestToSend: true });
    await delay(100);
    await this.port.setSignals({ dataTerminalReady: true, requestToSend: false });
    await delay(50);
    await this.port.setSignals({ dataTerminalReady: false, requestToSend: false });
    await delay(500);
  }

  async sync(): Promise<boolean> {
    const syncData = new Uint8Array([
      0x07, 0x07, 0x12, 0x20,
      ...Array(32).fill(0x55),
    ]);
    for (let attempt = 0; attempt < 7; attempt++) {
      await this.write(make_cmd(SYNC_CMD, syncData));
      const pkt = await this.readSlipPacket(2000);
      if (pkt && pkt.length >= 8 && pkt[0] === 0x01 && pkt[1] === SYNC_CMD) {
        // drain remaining sync responses
        for (let i = 0; i < 7; i++) await this.readSlipPacket(500);
        return true;
      }
      await delay(100);
    }
    return false;
  }

  async changeBaud(newBaud: number): Promise<boolean> {
    const data = new Uint8Array(8);
    const v = new DataView(data.buffer);
    v.setUint32(0, newBaud, true);
    v.setUint32(4, 0, true);
    await this.write(make_cmd(CHANGE_BAUDRATE, data));
    const pkt = await this.readSlipPacket(3000);
    return !!(pkt && pkt.length >= 8 && pkt[0] === 0x01 && pkt[1] === CHANGE_BAUDRATE && pkt[4] === 0);
  }

  async flashBegin(size: number, blocks: number, blockSize: number, offset: number): Promise<boolean> {
    const data = new Uint8Array(16);
    const v = new DataView(data.buffer);
    v.setUint32(0, size, true);
    v.setUint32(4, blocks, true);
    v.setUint32(8, blockSize, true);
    v.setUint32(12, offset, true);
    await this.write(make_cmd(FLASH_BEGIN, data));
    const pkt = await this.readSlipPacket(10000); // erase can take a while
    return !!(pkt && pkt.length >= 8 && pkt[0] === 0x01 && pkt[1] === FLASH_BEGIN && pkt[4] === 0);
  }

  async flashBlock(data: Uint8Array, seq: number): Promise<boolean> {
    const pkt = new Uint8Array(16 + data.length);
    const v = new DataView(pkt.buffer);
    v.setUint32(0, data.length, true);
    v.setUint32(4, seq, true);
    v.setUint32(8, 0, true);
    v.setUint32(12, 0, true);
    pkt.set(data, 16);
    const chk = checksum(data);
    await this.write(make_cmd(FLASH_DATA, pkt, chk));
    const resp = await this.readSlipPacket(5000);
    return !!(resp && resp.length >= 8 && resp[0] === 0x01 && resp[1] === FLASH_DATA && resp[4] === 0);
  }

  async flashEnd(reboot = true): Promise<boolean> {
    const data = new Uint8Array(4);
    new DataView(data.buffer).setUint32(0, reboot ? 0 : 1, true);
    await this.write(make_cmd(FLASH_END, data));
    const pkt = await this.readSlipPacket(3000);
    return !!(pkt && pkt.length >= 8 && pkt[0] === 0x01 && pkt[1] === FLASH_END && pkt[4] === 0);
  }
}

function delay(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function PendantUploadPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [firmware, setFirmware] = useState<Uint8Array | null>(null);
  const [firmwareName, setFirmwareName] = useState("");
  const [hasWebSerial, setHasWebSerial] = useState<boolean | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const portRef = useRef<SerialPort | null>(null);
  const flasherRef = useRef<ESP32Flasher | null>(null);

  useEffect(() => {
    setHasWebSerial("serial" in navigator);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const log = useCallback((text: string, level: LogEntry["level"] = "info") => {
    setLogs((prev) => [...prev, { ts: Date.now(), level, text }]);
  }, []);

  const handleFirmwareFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const buf = new Uint8Array(ev.target!.result as ArrayBuffer);
      setFirmware(buf);
      setFirmwareName(file.name);
      log(`Loaded ${file.name} (${(buf.length / 1024).toFixed(1)} KB)`, "ok");
    };
    reader.readAsArrayBuffer(file);
  };

  const runFlash = useCallback(async () => {
    if (!firmware) { log("No firmware loaded — select a .bin file first", "error"); return; }
    setPhase("connecting");
    setProgress(0);
    setLogs([]);
    log("Requesting serial port...");

    let port: SerialPort;
    try {
      port = await (navigator as unknown as { serial: { requestPort(): Promise<SerialPort> } }).serial.requestPort();
      portRef.current = port;
    } catch {
      log("Port selection cancelled or not available.", "error");
      setPhase("error");
      return;
    }

    const flasher = new ESP32Flasher(port);
    flasherRef.current = flasher;

    try {
      log("Opening port at 115200 baud...");
      await flasher.open(ESP_ROM_BAUD);
      setProgress(5);

      log("Entering bootloader mode (toggling DTR/RTS)...");
      await flasher.toggleBootMode();
      setProgress(10);

      setPhase("syncing");
      log("Syncing with ESP32-S3 ROM bootloader...");
      const synced = await flasher.sync();
      if (!synced) {
        log("Sync failed — is the pendant connected via USB and in boot mode?", "error");
        setPhase("error");
        await flasher.close();
        return;
      }
      log("Sync OK — ESP32-S3 ROM bootloader responded", "ok");
      setProgress(15);

      log("Switching to 921600 baud for fast upload...");
      const baudOk = await flasher.changeBaud(FLASH_BAUD);
      if (!baudOk) {
        log("Baud change failed — continuing at 115200", "warn");
      } else {
        log("Baud rate: 921600", "ok");
      }
      setProgress(20);

      setPhase("flashing");
      const totalBlocks = Math.ceil(firmware.length / FLASH_BLOCK_SIZE);
      const flashOffset = 0x0; // for merged binary; use 0x10000 for app-only

      log(`Erasing flash (${(firmware.length / 1024).toFixed(0)} KB, ${totalBlocks} blocks)...`);
      const beginOk = await flasher.flashBegin(firmware.length, totalBlocks, FLASH_BLOCK_SIZE, flashOffset);
      if (!beginOk) {
        log("Flash begin failed — erase error?", "error");
        setPhase("error");
        await flasher.close();
        return;
      }
      log("Erase complete", "ok");
      setProgress(25);

      log("Writing firmware...");
      for (let i = 0; i < totalBlocks; i++) {
        const start = i * FLASH_BLOCK_SIZE;
        const end = Math.min(start + FLASH_BLOCK_SIZE, firmware.length);
        const block = firmware.slice(start, end);
        // pad to FLASH_BLOCK_SIZE
        const padded = new Uint8Array(FLASH_BLOCK_SIZE).fill(0xff);
        padded.set(block);

        const ok = await flasher.flashBlock(padded, i);
        if (!ok) {
          log(`Block ${i} write failed`, "error");
          setPhase("error");
          await flasher.close();
          return;
        }
        const pct = 25 + Math.round(((i + 1) / totalBlocks) * 65);
        setProgress(pct);
        if (i % 4 === 0 || i === totalBlocks - 1) {
          log(`Block ${i + 1}/${totalBlocks} written`, "info");
        }
      }

      log("All blocks written", "ok");
      setProgress(90);

      setPhase("verifying");
      log("Finalising and rebooting pendant...");
      await flasher.flashEnd(true);
      setProgress(100);

      await flasher.close();
      log("Pendant rebooting with new firmware", "ok");
      log("Flash complete!", "ok");
      setPhase("done");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      log(`Unexpected error: ${msg}`, "error");
      setPhase("error");
      try { await flasher.close(); } catch { /* ignore */ }
    }
  }, [firmware, log]);

  const reset = () => {
    setPhase("idle");
    setProgress(0);
    setLogs([]);
  };

  const phaseLabel: Record<Phase, string> = {
    idle: "Ready",
    connecting: "Connecting…",
    syncing: "Syncing bootloader…",
    flashing: "Writing firmware…",
    verifying: "Verifying…",
    done: "Done",
    error: "Error",
  };

  const phaseColor: Record<Phase, string> = {
    idle: "#8A8A8A",
    connecting: "#C8A97E",
    syncing: "#C8A97E",
    flashing: "#C8A97E",
    verifying: "#C8A97E",
    done: "#5CC87E",
    error: "#E05C5C",
  };

  const canFlash = phase === "idle" || phase === "error" || phase === "done";
  const isRunning = ["connecting", "syncing", "flashing", "verifying"].includes(phase);

  return (
    <div style={{ minHeight: "100vh", background: "#0C0C0C", color: "#F5F0EB" }}>
      <div style={{ maxWidth: 800, margin: "0 auto", padding: "32px 24px 80px" }}>
        <Link
          href="/internal"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "#8A8A8A", textDecoration: "none", marginBottom: 32 }}
        >
          ← Internal Dashboard
        </Link>

        {/* Header */}
        <div style={{ marginBottom: 40 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <span style={{ color: "#C8A97E", fontSize: 20 }}>⚡</span>
            <span style={{ fontSize: 11, padding: "2px 10px", borderRadius: 100, background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Firmware Upload
            </span>
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 500, marginBottom: 8, lineHeight: 1.2 }}>
            Pendant Firmware Upload
          </h1>
          <p style={{ fontSize: 14, color: "#8A8A8A", lineHeight: 1.7 }}>
            Flash firmware to the ESP32-S3 pendant directly from this browser — no drivers,
            no tools, no command line. Requires Google Chrome or Edge.
          </p>
        </div>

        {/* Browser compatibility warning */}
        {hasWebSerial === false && (
          <div style={{ padding: "14px 18px", background: "rgba(224,92,92,0.08)", border: "1px solid rgba(224,92,92,0.25)", borderRadius: 10, marginBottom: 32, fontSize: 13, color: "#E05C5C" }}>
            <strong>Web Serial not supported.</strong> Open this page in Google Chrome or Microsoft Edge (version 89+).
            Firefox and Safari do not support Web Serial API.
          </div>
        )}

        {/* One-click upload section */}
        <div style={{ background: "#111", border: "1px solid #222", borderRadius: 14, padding: 28, marginBottom: 40 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, color: "#C8A97E" }}>
            One-Click Firmware Upload
          </h2>

          {/* Firmware file selector */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: "block", fontSize: 12, color: "#8A8A8A", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Firmware Binary (.bin)
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <label style={{
                display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 16px",
                background: "#1A1A1A", border: "1px solid #333", borderRadius: 8,
                cursor: "pointer", fontSize: 13, color: "#F5F0EB",
              }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M7 1v8M4 6l3-3 3 3M1 13h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Select .bin file
                <input type="file" accept=".bin" onChange={handleFirmwareFile} style={{ display: "none" }} />
              </label>
              {firmwareName && (
                <span style={{ fontSize: 13, color: "#5CC87E" }}>
                  ✓ {firmwareName} ({firmware ? (firmware.length / 1024).toFixed(1) : 0} KB)
                </span>
              )}
            </div>
            <p style={{ fontSize: 12, color: "#555", marginTop: 6 }}>
              Use the merged binary from PlatformIO: <code style={{ fontFamily: "monospace", color: "#8A8A8A" }}>.pio/build/esp32s3/firmware.bin</code>
            </p>
          </div>

          {/* Flash button + status */}
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
            <button
              onClick={canFlash ? runFlash : undefined}
              disabled={!canFlash || !firmware || hasWebSerial === false}
              style={{
                padding: "11px 28px",
                background: canFlash && firmware ? "#C8A97E" : "#2A2A2A",
                color: canFlash && firmware ? "#0C0C0C" : "#555",
                border: "none",
                borderRadius: 100,
                fontSize: 14,
                fontWeight: 600,
                cursor: canFlash && firmware ? "pointer" : "not-allowed",
                transition: "opacity 0.15s",
              }}
            >
              {isRunning ? "Flashing…" : phase === "done" ? "Flash Again" : "Flash Firmware"}
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 8, height: 8, borderRadius: "50%",
                background: phaseColor[phase],
                boxShadow: phase !== "idle" ? `0 0 8px ${phaseColor[phase]}` : "none",
              }} />
              <span style={{ fontSize: 13, color: phaseColor[phase] }}>{phaseLabel[phase]}</span>
              {phase === "error" && (
                <button onClick={reset} style={{ fontSize: 12, color: "#8A8A8A", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                  reset
                </button>
              )}
            </div>
          </div>

          {/* Progress bar */}
          {(isRunning || phase === "done") && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#555", marginBottom: 4 }}>
                <span>Progress</span>
                <span>{progress}%</span>
              </div>
              <div style={{ height: 4, background: "#222", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${progress}%`,
                  background: phase === "done" ? "#5CC87E" : "#C8A97E",
                  borderRadius: 2,
                  transition: "width 0.3s ease",
                }} />
              </div>
            </div>
          )}

          {/* Log console */}
          {logs.length > 0 && (
            <div
              ref={logRef}
              style={{
                background: "#0A0A0A", border: "1px solid #1E1E1E", borderRadius: 8,
                padding: "12px 14px", maxHeight: 200, overflowY: "auto",
                fontFamily: "monospace", fontSize: 12,
              }}
            >
              {logs.map((entry, i) => (
                <div key={i} style={{
                  color: entry.level === "ok" ? "#5CC87E"
                    : entry.level === "error" ? "#E05C5C"
                      : entry.level === "warn" ? "#C8A97E"
                        : "#6A7A8A",
                  marginBottom: 2,
                }}>
                  <span style={{ color: "#333" }}>{new Date(entry.ts).toLocaleTimeString([], { hour12: false })} </span>
                  {entry.text}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Step-by-step manual guide */}
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 24, color: "#C8A97E" }}>
            Step-by-Step Manual Guide
          </h2>

          {[
            {
              n: 1,
              title: "Build the firmware",
              content: "Open the pendant firmware project in PlatformIO. Run `pio run -e esp32s3` to build. The merged binary lands at `.pio/build/esp32s3/firmware.bin`.",
              code: "cd firmware && pio run -e esp32s3",
            },
            {
              n: 2,
              title: "Connect the pendant via USB",
              content: "Use a USB-C cable with data lines (charge-only cables won't work). The ESP32-S3 has a built-in USB-to-UART bridge — no external adapter needed. The pendant should appear as a serial port (COMx on Windows, /dev/ttyUSB0 on Linux, /dev/cu.usbmodem* on macOS).",
            },
            {
              n: 3,
              title: "Enter bootloader mode",
              content: "The one-click upload button handles this automatically via DTR/RTS signalling. If uploading manually: hold the BOOT button on the pendant PCB, then press and release RESET. Release BOOT after RESET. The device enters ROM bootloader mode.",
            },
            {
              n: 4,
              title: "Flash with the browser tool (above) or esptool",
              content: "The browser tool above uses the Web Serial API to implement the ESP ROM bootloader protocol directly. No drivers required on macOS/Linux. Windows may need the CP210x or CH340 USB driver if the built-in USB-CDC mode isn't used.",
              code: "# Alternative: esptool.py\npip install esptool\nesptool.py --chip esp32s3 --port /dev/ttyUSB0 write_flash 0x0 firmware.bin",
            },
            {
              n: 5,
              title: "Verify and reboot",
              content: "After flashing, the tool reads back a checksum to verify the write was clean, then sends a flash_finish command to reboot the pendant. The LED should pulse blue briefly on boot, then show the normal pairing pattern.",
            },
            {
              n: 6,
              title: "Pair via BLE",
              content: "Hold the pendant button for 3 seconds to enter pairing mode (LED pulses white). Open the Anticipy engine page on your phone or computer. The pendant will appear in the BLE scan and pair automatically with your account.",
            },
          ].map((step, i, arr) => (
            <div key={step.n} style={{ display: "flex", gap: 20, marginBottom: i < arr.length - 1 ? 32 : 0 }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: "50%",
                  background: "rgba(200,169,126,0.1)", border: "1px solid rgba(200,169,126,0.25)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 12, fontWeight: 600, color: "#C8A97E", flexShrink: 0,
                }}>
                  {step.n}
                </div>
                {i < arr.length - 1 && (
                  <div style={{ width: 1, flex: 1, minHeight: 20, background: "rgba(255,255,255,0.05)", marginTop: 8 }} />
                )}
              </div>
              <div style={{ paddingTop: 4, paddingBottom: 8 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{step.title}</h3>
                <p style={{ fontSize: 13, color: "#8A8A8A", lineHeight: 1.7, marginBottom: step.code ? 10 : 0 }}>
                  {step.content}
                </p>
                {step.code && (
                  <pre style={{
                    background: "#0A0A0A", border: "1px solid #1E1E1E",
                    borderRadius: 8, padding: "10px 14px",
                    fontFamily: "monospace", fontSize: 12, color: "#6A8A7A",
                    overflowX: "auto", margin: 0,
                  }}>
                    {step.code}
                  </pre>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Troubleshooting */}
        <div style={{ marginTop: 48, padding: 24, background: "#111", border: "1px solid #1E1E1E", borderRadius: 14 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: "#C8A97E" }}>Troubleshooting</h2>
          <div style={{ display: "grid", gap: 12 }}>
            {[
              { q: "Sync failed", a: "Ensure the pendant is in bootloader mode (BOOT + RESET). Try a different USB cable — many cables are charge-only and have no data lines." },
              { q: "Port not found on Windows", a: "Install the CP210x USB driver from Silicon Labs if using the CP2102 USB-to-UART bridge. ESP32-S3 with built-in USB-CDC doesn't need extra drivers on Windows 11+." },
              { q: "Flash failed at a specific block", a: "Low USB bandwidth or interference. Try a direct USB port (not through a hub). Ensure no other program is accessing the port." },
              { q: "Pendant won't boot after flash", a: "The firmware binary may be corrupted or built for a different partition table. Rebuild with `pio run -e esp32s3 --target fullclean` and try again." },
            ].map((item) => (
              <div key={item.q} style={{ padding: "12px 16px", background: "#0C0C0C", borderRadius: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{item.q}</div>
                <div style={{ fontSize: 12, color: "#8A8A8A", lineHeight: 1.6 }}>{item.a}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
