// holder — a SEPARATE PROCESS that holds the default input device, standing in
// for "Zoom/Meet/Teams has the microphone open".
//   plain : AVAudioEngine input on the plain HAL IO path
//   vpio  : AVAudioEngine input with Voice-Processing IO (AEC/AGC/NS) --
//           the audio unit conferencing apps actually use
//   hog   : takes kAudioDevicePropertyHogMode on the input device -- the
//           pessimistic bound, exclusive access
import AVFoundation
import CoreAudio
import Foundation

let mode = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "plain"
let sys = AudioObjectID(kAudioObjectSystemObject)
func addr(_ s: AudioObjectPropertySelector,
          _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal)
-> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: s, mScope: scope,
                               mElement: kAudioObjectPropertyElementMain)
}
func defaultInputDevice() -> AudioDeviceID {
    var a = addr(kAudioHardwarePropertyDefaultInputDevice)
    var d = AudioDeviceID(0); var s = UInt32(MemoryLayout<AudioDeviceID>.size)
    _ = AudioObjectGetPropertyData(sys, &a, 0, nil, &s, &d); return d
}
func deviceName(_ d: AudioDeviceID) -> String {
    var a = addr(kAudioObjectPropertyName)
    var v: Unmanaged<CFString>? = nil; var s = UInt32(MemoryLayout<CFString?>.size)
    guard AudioObjectGetPropertyData(d, &a, 0, nil, &s, &v) == noErr,
          let v else { return "?" }
    return v.takeRetainedValue() as String
}

let dev = defaultInputDevice()
print("holder mode=\(mode) pid=\(getpid()) inputDevice=\(dev) \"\(deviceName(dev))\"")
fflush(stdout)

if mode == "hog" {
    var pid = pid_t(getpid())
    var okScope = "none"
    for scope in [kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyScopeInput] {
        var a = addr(kAudioDevicePropertyHogMode, scope)
        let st = AudioObjectSetPropertyData(dev, &a, 0, nil,
                    UInt32(MemoryLayout<pid_t>.size), &pid)
        var back: pid_t = -1; var s = UInt32(MemoryLayout<pid_t>.size)
        _ = AudioObjectGetPropertyData(dev, &a, 0, nil, &s, &back)
        print("  hog set scope=\(scope == kAudioObjectPropertyScopeGlobal ? "global" : "input") status=\(st) readback_owner_pid=\(back)")
        if st == noErr && back == pid { okScope = "ok" }
    }
    print("  hog result: \(okScope)")
    fflush(stdout)
}

let engine = AVAudioEngine()
let input = engine.inputNode
if mode == "vpio" {
    do { try input.setVoiceProcessingEnabled(true)
         print("  voice processing: ENABLED (kAudioUnitSubType_VoiceProcessingIO)") }
    catch { print("  voice processing: FAILED \(error)") }
}
let fmt = input.outputFormat(forBus: 0)
print("  NEAR-holder format: \(Int(fmt.sampleRate)) Hz, \(fmt.channelCount) ch")
var count = 0
let lock = NSLock()
input.installTap(onBus: 0, bufferSize: 4096, format: fmt) { _, _ in
    lock.lock(); count += 1; lock.unlock()
}
do { try engine.start() } catch {
    print("  HOLDER FAILED TO START: \(error)"); fflush(stdout); exit(3)
}
print("  holder running, holding the input device"); fflush(stdout)
var last = 0
for _ in 0..<600 {
    Thread.sleep(forTimeInterval: 1.0)
    lock.lock(); let c = count; lock.unlock()
    print("  holder t+: buffers=\(c) (+\(c - last))"); fflush(stdout); last = c
}
