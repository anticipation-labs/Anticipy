// Minimal, dependency-free ZIP writer (STORE method — no compression).
//
// Why hand-rolled: the download route must serve the real dev .app bundle
// (a directory) as a single file. A .zip of the .app is the standard macOS
// hand-off form and is exactly what Apple notarization later staples to. The
// app has no zip dependency in package.json and the task is surgical, so we
// build the (simple, well-specified) ZIP container ourselves with STORE so the
// bytes inside the bundle — including the executable — are preserved verbatim.
//
// This is NOT signing and NOT notarization (those stay Omar-gated): it is a
// faithful archive of the honest, unsigned developer-preview build.

import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

// CRC-32 (IEEE) — required by the ZIP spec for each entry.
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(buf) {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc = CRC_TABLE[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// MS-DOS date/time (we use a fixed, deterministic stamp — content is what matters).
const DOS_TIME = 0;
const DOS_DATE = ((2026 - 1980) << 9) | (1 << 5) | 1; // 2026-01-01

function collectFiles(rootDir, baseName) {
  // Returns [{ name (zip path, '/'-separated), abs, mode }] for every regular
  // file under rootDir, with names prefixed by baseName (e.g. "Anticipy.app/...").
  const out = [];
  const walk = (absDir, relDir) => {
    const entries = fs.readdirSync(absDir, { withFileTypes: true }).sort((a, b) =>
      a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
    );
    for (const entry of entries) {
      const abs = path.join(absDir, entry.name);
      const rel = relDir ? `${relDir}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        walk(abs, rel);
      } else if (entry.isFile()) {
        const mode = fs.statSync(abs).mode;
        out.push({ name: `${baseName}/${rel}`, abs, mode });
      }
    }
  };
  walk(rootDir, "");
  return out;
}

// Build a ZIP (STORE) of a directory tree. Preserves Unix file modes (the
// executable bit on the app binary) via the external-attributes field.
export function zipDirectory(rootDir, baseName) {
  const files = collectFiles(rootDir, baseName);
  const localChunks = [];
  const centralChunks = [];
  let offset = 0;

  for (const file of files) {
    const data = fs.readFileSync(file.abs);
    const nameBuf = Buffer.from(file.name, "utf8");
    const crc = crc32(data);
    const size = data.length;

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); // local file header signature
    local.writeUInt16LE(20, 4); // version needed
    local.writeUInt16LE(0, 6); // flags
    local.writeUInt16LE(0, 8); // method 0 = STORE
    local.writeUInt16LE(DOS_TIME, 10);
    local.writeUInt16LE(DOS_DATE, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(size, 18); // compressed size (== size for STORE)
    local.writeUInt32LE(size, 22); // uncompressed size
    local.writeUInt16LE(nameBuf.length, 26);
    local.writeUInt16LE(0, 28); // extra length
    localChunks.push(local, nameBuf, data);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); // central directory header signature
    central.writeUInt16LE(0x031e, 4); // version made by (0x03 = unix, 0x1e = v3.0)
    central.writeUInt16LE(20, 6); // version needed
    central.writeUInt16LE(0, 8); // flags
    central.writeUInt16LE(0, 10); // method
    central.writeUInt16LE(DOS_TIME, 12);
    central.writeUInt16LE(DOS_DATE, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(size, 20);
    central.writeUInt32LE(size, 24);
    central.writeUInt16LE(nameBuf.length, 28);
    central.writeUInt16LE(0, 30); // extra length
    central.writeUInt16LE(0, 32); // comment length
    central.writeUInt16LE(0, 34); // disk number
    central.writeUInt16LE(0, 36); // internal attrs
    // external attrs: Unix mode in high 16 bits so the exec bit survives.
    central.writeUInt32LE(((file.mode & 0xffff) >>> 0) * 0x10000, 38);
    central.writeUInt32LE(offset, 42); // local header offset
    centralChunks.push(central, nameBuf);

    offset += local.length + nameBuf.length + data.length;
  }

  const centralDir = Buffer.concat(centralChunks);
  const centralSize = centralDir.length;
  const centralOffset = offset;

  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); // end of central directory signature
  end.writeUInt16LE(0, 4); // disk number
  end.writeUInt16LE(0, 6); // central dir start disk
  end.writeUInt16LE(files.length, 8); // entries this disk
  end.writeUInt16LE(files.length, 10); // total entries
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(centralOffset, 16);
  end.writeUInt16LE(0, 20); // comment length

  return Buffer.concat([...localChunks, centralDir, end]);
}

// Used only to keep zlib imported for potential future DEFLATE; STORE is
// intentional here so the archive is byte-faithful and trivially verifiable.
export const _zlib = zlib;
