// audioprocs — enumerate Core Audio process objects and their input/output IO state.
// This is exactly the §6.2 detection signal: which PROCESS holds which STREAM.
// It reads no audio and cannot know what anybody said.
import CoreAudio
import Foundation

let sys = AudioObjectID(kAudioObjectSystemObject)

func addr(_ s: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: s,
                               mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

func processObjects() -> [AudioObjectID] {
    var a = addr(kAudioHardwarePropertyProcessObjectList)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(sys, &a, 0, nil, &size) == noErr, size > 0 else { return [] }
    let n = Int(size) / MemoryLayout<AudioObjectID>.size
    var ids = [AudioObjectID](repeating: 0, count: n)
    guard AudioObjectGetPropertyData(sys, &a, 0, nil, &size, &ids) == noErr else { return [] }
    return ids
}

func u32(_ obj: AudioObjectID, _ sel: AudioObjectPropertySelector) -> UInt32? {
    var a = addr(sel); var v: UInt32 = 0; var s = UInt32(MemoryLayout<UInt32>.size)
    return AudioObjectGetPropertyData(obj, &a, 0, nil, &s, &v) == noErr ? v : nil
}
func i32(_ obj: AudioObjectID, _ sel: AudioObjectPropertySelector) -> Int32? {
    var a = addr(sel); var v: Int32 = 0; var s = UInt32(MemoryLayout<Int32>.size)
    return AudioObjectGetPropertyData(obj, &a, 0, nil, &s, &v) == noErr ? v : nil
}
func str(_ obj: AudioObjectID, _ sel: AudioObjectPropertySelector) -> String? {
    var a = addr(sel); var v: CFString? = nil; var s = UInt32(MemoryLayout<CFString?>.size)
    guard AudioObjectGetPropertyData(obj, &a, 0, nil, &s, &v) == noErr else { return nil }
    return v as String?
}

let objs = processObjects()
print("process objects: \(objs.count)")
print(String(format: "%-8s %-8s %-6s %-6s %s", ("objID" as NSString).utf8String!,
             ("pid" as NSString).utf8String!, ("in" as NSString).utf8String!,
             ("out" as NSString).utf8String!, ("bundle / name" as NSString).utf8String!))
for o in objs {
    let pid = i32(o, kAudioProcessPropertyPID) ?? -1
    let inp = u32(o, kAudioProcessPropertyIsRunningInput) ?? 0
    let outp = u32(o, kAudioProcessPropertyIsRunningOutput) ?? 0
    var label = str(o, kAudioProcessPropertyBundleID) ?? ""
    if label.isEmpty, pid > 0 {
        let p = Process(); p.executableURL = URL(fileURLWithPath: "/bin/ps")
        p.arguments = ["-o", "comm=", "-p", "\(pid)"]
        let pipe = Pipe(); p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        if (try? p.run()) != nil { p.waitUntilExit()
            label = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? "" }
    }
    // Only print processes doing IO, unless --all
    let showAll = CommandLine.arguments.contains("--all")
    if showAll || inp == 1 || outp == 1 {
        print(String(format: "%-8u %-8d %-6u %-6u %@", o, pid, inp, outp, label))
    }
}
