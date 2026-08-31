import AVFoundation
import AudioToolbox
import CoreAudio
import Foundation

/// Thread-safe counters shared by the real-time audio callbacks and the UI's
/// health timer. The callback only performs bounded arithmetic and never
/// touches SwiftUI state.
final class AudioCaptureMeter: @unchecked Sendable {
    private let lock = NSLock()
    private var buffers = 0
    private var frames: Int64 = 0
    private var peak: Float = 0
    private var everDelivered = false
    private var everNonZero = false

    func record(_ buffer: AVAudioPCMBuffer) {
        var bufferPeak: Float = 0
        if let channels = buffer.floatChannelData {
            let frameCount = Int(buffer.frameLength)
            for channel in 0..<Int(buffer.format.channelCount) {
                let samples = channels[channel]
                for frame in 0..<frameCount {
                    bufferPeak = max(bufferPeak, abs(samples[frame]))
                }
            }
        }
        lock.lock()
        buffers += 1
        frames += Int64(buffer.frameLength)
        peak = max(peak, bufferPeak)
        everDelivered = true
        if bufferPeak > 0 { everNonZero = true }
        lock.unlock()
    }

    func takeWindow(elapsedSeconds: Double,
                    expectedSampleRate: Double) -> CaptureStreamWindow {
        lock.lock()
        let window = CaptureStreamWindow(buffers: buffers, frames: frames,
                                         peakAmplitude: peak,
                                         elapsedSeconds: elapsedSeconds,
                                         expectedSampleRate: expectedSampleRate)
        buffers = 0
        frames = 0
        peak = 0
        lock.unlock()
        return window
    }

    var hasEverDelivered: Bool {
        lock.lock(); defer { lock.unlock() }
        return everDelivered
    }

    var hasEverCarriedSignal: Bool {
        lock.lock(); defer { lock.unlock() }
        return everNonZero
    }
}

enum SystemAudioCaptureError: LocalizedError {
    case cannotResolveSelf(OSStatus)
    case cannotCreateTap(OSStatus)
    case cannotReadTapUID(OSStatus)
    case cannotReadTapFormat(OSStatus)
    case invalidTapFormat
    case cannotCreateAggregate(OSStatus)
    case cannotCreateIOProc(OSStatus)
    case cannotStartDevice(OSStatus)

    var errorDescription: String? {
        switch self {
        case .cannotResolveSelf(let status):
            return "Anticipy could not identify its own audio process (Core Audio \(status))."
        case .cannotCreateTap(let status):
            return "System audio could not be opened (Core Audio \(status)). Check Privacy & Security > Screen & System Audio Recording."
        case .cannotReadTapUID(let status):
            return "The system-audio tap opened without an identity (Core Audio \(status))."
        case .cannotReadTapFormat(let status):
            return "The system-audio tap opened without a readable format (Core Audio \(status))."
        case .invalidTapFormat:
            return "The system-audio tap returned an unusable audio format."
        case .cannotCreateAggregate(let status):
            return "The private system-audio device could not be created (Core Audio \(status))."
        case .cannotCreateIOProc(let status):
            return "The system-audio reader could not be attached (Core Audio \(status))."
        case .cannotStartDevice(let status):
            return "The system-audio reader could not start (Core Audio \(status))."
        }
    }
}

/// Captures everything the owner can hear from the Mac, without muting it.
///
/// This is deliberately a global tap rather than a tap tied to Chrome's
/// current Helper PID. Chrome replaces that process during updates, crashes,
/// device changes, and ordinary renderer churn. A global tap keeps carrying
/// the replacement process; process restoration and the bundle exclusion keep
/// Anticipy itself out of its own recording.
@available(macOS 26.0, *)
final class SystemAudioCapture: @unchecked Sendable {
    typealias BufferHandler = @Sendable (AVAudioPCMBuffer) -> Void

    private let lock = NSLock()
    private let callbackQueue = DispatchQueue(label: "ai.anticipy.mac.system-audio",
                                              qos: .userInitiated)
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private let systemObject = AudioObjectID(kAudioObjectSystemObject)

    func start(onBuffer: @escaping BufferHandler) throws -> AVAudioFormat {
        stop()

        guard let selfObject = processObject(for: ProcessInfo.processInfo.processIdentifier) else {
            throw SystemAudioCaptureError.cannotResolveSelf(-1)
        }

        let description = CATapDescription(
            stereoGlobalTapButExcludeProcesses: [selfObject])
        description.uuid = UUID()
        description.name = "Anticipy meeting system audio"
        description.isPrivate = true
        description.muteBehavior = .unmuted
        description.bundleIDs = [Bundle.main.bundleIdentifier ?? "ai.anticipy.mac"]
        description.isProcessRestoreEnabled = true

        var newTap = AudioObjectID(kAudioObjectUnknown)
        let tapStatus = AudioHardwareCreateProcessTap(description, &newTap)
        guard tapStatus == noErr, newTap != kAudioObjectUnknown else {
            throw SystemAudioCaptureError.cannotCreateTap(tapStatus)
        }
        tapID = newTap

        do {
            let tapUID = try readTapUID(newTap)
            var streamDescription = try readTapFormat(newTap)
            guard let format = AVAudioFormat(streamDescription: &streamDescription),
                  format.sampleRate > 0, format.channelCount > 0 else {
                throw SystemAudioCaptureError.invalidTapFormat
            }

            let aggregateDescription: [String: Any] = [
                kAudioAggregateDeviceNameKey: "Anticipy private system-audio device",
                kAudioAggregateDeviceUIDKey: UUID().uuidString,
                kAudioAggregateDeviceIsPrivateKey: true,
                kAudioAggregateDeviceIsStackedKey: false,
                kAudioAggregateDeviceTapAutoStartKey: true,
                kAudioAggregateDeviceSubDeviceListKey: [[String: Any]](),
                kAudioAggregateDeviceTapListKey: [[
                    kAudioSubTapUIDKey: tapUID,
                    kAudioSubTapDriftCompensationKey: true,
                ]],
            ]
            var newAggregate = AudioObjectID(kAudioObjectUnknown)
            let aggregateStatus = AudioHardwareCreateAggregateDevice(
                aggregateDescription as CFDictionary, &newAggregate)
            guard aggregateStatus == noErr, newAggregate != kAudioObjectUnknown else {
                throw SystemAudioCaptureError.cannotCreateAggregate(aggregateStatus)
            }
            aggregateID = newAggregate

            var newIOProc: AudioDeviceIOProcID?
            let ioStatus = AudioDeviceCreateIOProcIDWithBlock(
                &newIOProc, newAggregate, callbackQueue) { _, inputData, _, _, _ in
                    guard let buffer = SystemAudioCapture.copyBuffer(
                        inputData, format: format) else { return }
                    onBuffer(buffer)
                }
            guard ioStatus == noErr, let newIOProc else {
                throw SystemAudioCaptureError.cannotCreateIOProc(ioStatus)
            }
            ioProcID = newIOProc

            let startStatus = AudioDeviceStart(newAggregate, newIOProc)
            guard startStatus == noErr else {
                throw SystemAudioCaptureError.cannotStartDevice(startStatus)
            }
            return format
        } catch {
            stop()
            throw error
        }
    }

    func stop() {
        lock.lock()
        let aggregate = aggregateID
        let tap = tapID
        let ioProc = ioProcID
        aggregateID = AudioObjectID(kAudioObjectUnknown)
        tapID = AudioObjectID(kAudioObjectUnknown)
        ioProcID = nil
        lock.unlock()

        if aggregate != kAudioObjectUnknown {
            if let ioProc {
                AudioDeviceStop(aggregate, ioProc)
                AudioDeviceDestroyIOProcID(aggregate, ioProc)
            }
            AudioHardwareDestroyAggregateDevice(aggregate)
        }
        if tap != kAudioObjectUnknown {
            AudioHardwareDestroyProcessTap(tap)
        }
    }

    private func processObject(for pid: pid_t) -> AudioObjectID? {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var processID = pid
        var object = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = AudioObjectGetPropertyData(
            systemObject, &address, UInt32(MemoryLayout<pid_t>.size),
            &processID, &size, &object)
        guard status == noErr, object != kAudioObjectUnknown else { return nil }
        return object
    }

    private func readTapUID(_ tap: AudioObjectID) throws -> String {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioTapPropertyUID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var unmanaged: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<CFString?>.size)
        let status = AudioObjectGetPropertyData(tap, &address, 0, nil,
                                                &size, &unmanaged)
        guard status == noErr, let unmanaged else {
            throw SystemAudioCaptureError.cannotReadTapUID(status)
        }
        return unmanaged.takeRetainedValue() as String
    }

    private func readTapFormat(_ tap: AudioObjectID) throws -> AudioStreamBasicDescription {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioTapPropertyFormat,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var format = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        let status = AudioObjectGetPropertyData(tap, &address, 0, nil,
                                                &size, &format)
        guard status == noErr else {
            throw SystemAudioCaptureError.cannotReadTapFormat(status)
        }
        return format
    }

    private static func copyBuffer(_ input: UnsafePointer<AudioBufferList>,
                                   format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let source = UnsafeMutableAudioBufferListPointer(
            UnsafeMutablePointer(mutating: input))
        guard let first = source.first else { return nil }
        let bytesPerFrame = max(1, Int(format.streamDescription.pointee.mBytesPerFrame))
        let frameCount = AVAudioFrameCount(Int(first.mDataByteSize) / bytesPerFrame)
        guard frameCount > 0,
              let copy = AVAudioPCMBuffer(pcmFormat: format,
                                          frameCapacity: frameCount) else { return nil }
        copy.frameLength = frameCount
        let destination = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        guard source.count == destination.count else { return nil }
        for index in source.indices {
            guard let src = source[index].mData,
                  let dst = destination[index].mData else { continue }
            let byteCount = min(Int(source[index].mDataByteSize),
                                Int(destination[index].mDataByteSize))
            memcpy(dst, src, byteCount)
            destination[index].mDataByteSize = UInt32(byteCount)
        }
        return copy
    }

    deinit { stop() }
}
