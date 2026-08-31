#!/bin/sh
# The route-change crash contract, checked at both boundaries:
#
#   sh app/ios/Tests/run_audio_recovery_tests.sh
#
# AVAudioNode allows one tap per bus and enforces that rule with NSException.
# Builds 75, 109 and 111 all terminated in InstallTapOnNode from the route
# notification -> recoverAudio -> configureAndStartEngine path. The simulator
# cannot produce a real iPhone route transition, so this gate proves the two
# structural properties that remove that crash path, then executes the narrow
# Objective-C exception boundary itself.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
listener="$app/Audio/PhoneListener.swift"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

[ -f "$listener" ] || { echo "missing $listener"; exit 2; }
code="$out/PhoneListener.swift"
grep -v '^[[:space:]]*//' "$listener" > "$code"

block() {
    awk -v start="$1" -v end="$2" '
        $0 ~ start { inb = 1 }
        inb { print }
        inb && $0 == end { exit }
    ' "$code"
}

configure=$(block 'private func configureAndStartEngine' '    }')
route=$(block 'AVAudioSession.routeChangeNotification' '        }')
retry=$(block 'private func retryCapture' '    }')
recover=$(block 'private func recoverAudio' '    }')
replace=$(block 'private func replaceCaptureEngine' '    }')
stop=$(block '^[[:space:]]*func stop[(][)][[:space:]]*[{]' '    }')

for named in configure route retry recover replace stop; do
    eval "body=\${$named}"
    [ -n "$body" ] || {
        echo "The audio recovery gate can no longer find $named."
        echo "Its rules would otherwise search an empty string and pass."
        exit 2
    }
done

case "$route" in
    *scheduleAudioRecovery* ) ;;
    * ) echo "The route observer rebuilds audio inside AVAudioSession's notification stack."
        exit 1 ;;
esac
case "$route" in
    *self.recoverAudio* )
        echo "The route observer calls recoverAudio synchronously again."
        exit 1 ;;
esac

case "$replace" in
    *'engine = AVAudioEngine()'* ) ;;
    * ) echo "Audio recovery reuses the tap-bearing AVAudioEngine."
        exit 1 ;;
esac
case "$retry:$recover" in
    *replaceCaptureEngine*:*replaceCaptureEngine* ) ;;
    * ) echo "Every retry and recovery must replace the old capture engine."
        exit 1 ;;
esac

case "$configure" in
    *AudioTapExceptionShield.perform*installTap*'guard installed else'* ) ;;
    * ) echo "installTap is no longer contained by the Objective-C exception shield."
        exit 1 ;;
esac
case "$configure" in
    *input.removeTap* )
        echo "configureAndStartEngine reinstalls a tap on the same input node."
        exit 1 ;;
esac
case "$stop" in
    *'if tapInstalled'*removeTap* ) ;;
    * ) echo "Stop removes a tap without proving this engine installed one."
        exit 1 ;;
esac

xcrun clang -fobjc-arc -framework Foundation \
    "$app/Audio/AudioTapExceptionShield.m" \
    "$here/AudioTapExceptionShieldTests.m" \
    -o "$out/audio-tap-exception-tests"
"$out/audio-tap-exception-tests"

echo "audio recovery contract: route work is deferred, every rebuild gets a"
echo "fresh input bus, and a transient installTap exception cannot end the app"
