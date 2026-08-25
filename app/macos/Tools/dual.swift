// dual -- opens NEAR (AVAudioEngine microphone tap) and FAR (Core Audio process
// tap drained through a tap-bearing aggregate device) and reports, per second,
// whether BOTH are delivering buffers at the same time.
//   dual --seconds 12 [--tap-pid <pid>] [--vpio] [--near-only] [--far-only]
import AVFoundation
import CoreAudio
import AudioToolbox
import Foundation

let args = CommandLine.arguments
func flag(_ n: String) -> Bool { args.contains(n) }
func val(_ n: String) -> String? {
    guard let i = args.firstIndex(of: n), i + 1 < args.count else { return nil }
    return args[i + 1]
}
let seconds = Int(val("--seconds") ?? "12") ?? 12
let tapPID = Int32(val("--tap-pid") ?? "") ?? -1
if let lp = val("--log") { freopen(lp, "w", stdout); freopen(lp, "a", stderr) }
setvbuf(stdout, nil, _IONBF, 0)
let sys = AudioObjectID(kAudioObjectSystemObject)

func addr(_ s: AudioObjectPropertySelector,
          _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal)
-> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: s, mScope: scope,
                               mElement: kAudioObjectPropertyElementMain)
}

// ------------------------------------------------------------ shared counters
final class Counter: @unchecked Sendable {
    private let lock = NSLock()
    private(set) var buffers = 0
    private(set) var frames: Int64 = 0
    private(set) var peak: Float = 0
    func add(_ f: Int64, _ p: Float) {
        lock.lock(); buffers += 1; frames += f; peak = max(peak, p); lock.unlock()
    }
    func snapshot() -> (Int, Int64, Float) {
        lock.lock(); defer { lock.unlock() }; return (buffers, frames, peak)
    }
    func resetPeak() { lock.lock(); peak = 0; lock.unlock() }
}
let near = Counter(), far = Counter()
final class Once: @unchecked Sendable {
    private let lock = NSLock(); var text: String? = nil
    func set(_ t: @autoclosure () -> String) {
        lock.lock(); if text == nil { text = t() }; lock.unlock() }
}
let farShape = Once()

// ------------------------------------------------------------------- NEAR
var engine: AVAudioEngine? = nil
var nearStatus = "not attempted"
if !flag("--far-only") {
    let e = AVAudioEngine()
    let input = e.inputNode
    if flag("--vpio") {
        do { try input.setVoiceProcessingEnabled(true) } catch {
            print("NEAR: voice processing failed: \(error)") }
    }
    let fmt = input.outputFormat(forBus: 0)
    print("NEAR format: \(Int(fmt.sampleRate)) Hz, \(fmt.channelCount) ch")
    if fmt.sampleRate == 0 || fmt.channelCount == 0 {
        nearStatus = "FAILED: input format is \(fmt.sampleRate) Hz / \(fmt.channelCount) ch"
    } else {
        input.installTap(onBus: 0, bufferSize: 4096, format: fmt) { buf, _ in
            var p: Float = 0
            if let ch = buf.floatChannelData {
                let n = Int(buf.frameLength)
                for c in 0..<Int(buf.format.channelCount) {
                    for i in 0..<n { p = max(p, abs(ch[c][i])) }
                }
            }
            near.add(Int64(buf.frameLength), p)
        }
        do { try e.start(); engine = e; nearStatus = "started" }
        catch { nearStatus = "FAILED to start: \(error)" }
    }
    print("NEAR: \(nearStatus)")
}

// -------------------------------------------------------------------- FAR
var tapID = AudioObjectID(kAudioObjectUnknown)
var aggID = AudioObjectID(kAudioObjectUnknown)
var ioProc: AudioDeviceIOProcID? = nil
var farStatus = "not attempted"

func processObject(for pid: pid_t) -> AudioObjectID? {
    var a = addr(kAudioHardwarePropertyTranslatePIDToProcessObject)
    var p = pid
    var obj = AudioObjectID(kAudioObjectUnknown)
    var s = UInt32(MemoryLayout<AudioObjectID>.size)
    let st = AudioObjectGetPropertyData(sys, &a, UInt32(MemoryLayout<pid_t>.size), &p, &s, &obj)
    guard st == noErr, obj != kAudioObjectUnknown else {
        print("FAR: PID->AudioObjectID translate failed status=\(st)"); return nil }
    return obj
}

if !flag("--near-only") {
    var targets: [AudioObjectID] = []
    if tapPID > 0, let o = processObject(for: tapPID) {
        targets = [o]
        print("FAR: tapping pid \(tapPID) -> AudioObjectID \(o)")
    } else if tapPID > 0 {
        farStatus = "FAILED: could not resolve pid \(tapPID) to a process object"
    }
    if farStatus == "not attempted" {
        let d = CATapDescription(stereoMixdownOfProcesses: targets)
        d.uuid = UUID()
        d.name = "Anticipy concurrent-capture probe"
        d.isPrivate = true
        d.muteBehavior = CATapMuteBehavior.unmuted
        let st = AudioHardwareCreateProcessTap(d, &tapID)
        if st != noErr || tapID == kAudioObjectUnknown {
            farStatus = "FAILED: AudioHardwareCreateProcessTap status=\(st)"
        } else {
            print("FAR: tap created, AudioObjectID=\(tapID)")
            var ua = addr(kAudioTapPropertyUID)
            var uref: Unmanaged<CFString>? = nil
            var us = UInt32(MemoryLayout<CFString?>.size)
            let ust = AudioObjectGetPropertyData(tapID, &ua, 0, nil, &us, &uref)
            guard ust == noErr, let uref else {
                farStatus = "FAILED: could not read tap UID status=\(ust)"
                print("FAR: \(farStatus)"); exit(4)
            }
            let tapUID = uref.takeRetainedValue() as String
            var fa = addr(kAudioTapPropertyFormat)
            var asbd = AudioStreamBasicDescription()
            var fs = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
            let fst = AudioObjectGetPropertyData(tapID, &fa, 0, nil, &fs, &asbd)
            print("FAR tap format: status=\(fst) \(Int(asbd.mSampleRate)) Hz, \(asbd.mChannelsPerFrame) ch, flags=\(asbd.mFormatFlags)")

            let aggUID = UUID().uuidString
            let desc: [String: Any] = [
                kAudioAggregateDeviceNameKey: "Anticipy Probe Aggregate",
                kAudioAggregateDeviceUIDKey: aggUID,
                kAudioAggregateDeviceIsPrivateKey: true,
                kAudioAggregateDeviceIsStackedKey: false,
                kAudioAggregateDeviceTapAutoStartKey: true,
                kAudioAggregateDeviceSubDeviceListKey: [[String: Any]](),
                kAudioAggregateDeviceTapListKey: [[
                    kAudioSubTapUIDKey: tapUID,
                    kAudioSubTapDriftCompensationKey: true,
                ]],
            ]
            let ast = AudioHardwareCreateAggregateDevice(desc as CFDictionary, &aggID)
            if ast != noErr || aggID == kAudioObjectUnknown {
                farStatus = "FAILED: AudioHardwareCreateAggregateDevice status=\(ast)"
            } else {
                print("FAR: aggregate device \(aggID) created")
                let sr = asbd.mSampleRate > 0 ? asbd.mSampleRate : 48000
                let ch = Int(asbd.mChannelsPerFrame > 0 ? asbd.mChannelsPerFrame : 2)
                let cst = AudioDeviceCreateIOProcIDWithBlock(&ioProc, aggID, nil) {
                    _, inData, _, _, _ in
                    let abl = UnsafeMutableAudioBufferListPointer(
                        UnsafeMutablePointer(mutating: inData))
                    var p: Float = 0
                    var frames: Int64 = 0
                    farShape.set("mNumberBuffers=\(abl.count) " + abl.map {
                        "[ch=\($0.mNumberChannels) bytes=\($0.mDataByteSize) data=\($0.mData != nil)]"
                    }.joined(separator: " "))
                    for b in abl {
                        guard let d = b.mData else { continue }
                        let n = Int(b.mDataByteSize) / MemoryLayout<Float>.size
                        frames = max(frames, Int64(n / max(1, Int(b.mNumberChannels))))
                        let f = d.assumingMemoryBound(to: Float.self)
                        for i in 0..<n { p = max(p, abs(f[i])) }
                    }
                    far.add(frames, p)
                }
                if cst != noErr {
                    farStatus = "FAILED: AudioDeviceCreateIOProcIDWithBlock status=\(cst)"
                } else {
                    let sst = AudioDeviceStart(aggID, ioProc)
                    farStatus = sst == noErr ? "started (\(Int(sr)) Hz, \(ch) ch)"
                                             : "FAILED: AudioDeviceStart status=\(sst)"
                }
            }
        }
    }
    print("FAR: \(farStatus)")
}

// ------------------------------------------------------------------- report
print("")
print("  t   NEAR buf  (+d)   NEARpk   FAR buf  (+d)   FARpk   both?")
var lastN = 0, lastF = 0
var bothSeconds = 0
for t in 1...seconds {
    Thread.sleep(forTimeInterval: 1.0)
    let (nb, _, np) = near.snapshot()
    let (fb, _, fp) = far.snapshot()
    let dn = nb - lastN, df = fb - lastF
    lastN = nb; lastF = fb
    let both = dn > 0 && df > 0
    if both { bothSeconds += 1 }
    print(String(format: "%3d   %7d (%+5d)  %7.4f   %7d (%+5d)  %7.4f   %@",
                 t, nb, dn, np, fb, df, fp, both ? "YES" : "no"))
    near.resetPeak(); far.resetPeak()
    fflush(stdout)
}

let (nb, nf, _) = near.snapshot()
let (fb, ff, _) = far.snapshot()
print("")
print("SUMMARY")
print("  NEAR: \(nearStatus) | buffers=\(nb) frames=\(nf)")
print("  FAR : \(farStatus) | buffers=\(fb) frames=\(ff)")
print("  seconds in which BOTH delivered: \(bothSeconds)/\(seconds)")
print("  FAR first-callback buffer list: \(farShape.text ?? "never called")")

if aggID != kAudioObjectUnknown {
    if let ioProc { AudioDeviceStop(aggID, ioProc); AudioDeviceDestroyIOProcID(aggID, ioProc) }
    AudioHardwareDestroyAggregateDevice(aggID)
}
if tapID != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tapID) }
engine?.stop()

// exit code: 0 only when both streams delivered concurrently for a majority of seconds
exit(bothSeconds * 2 > seconds ? 0 : 1)
