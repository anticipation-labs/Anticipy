#!/bin/sh
# Whose phone is this, and what does it still remember about them?
#
#   sh app/ios/Tests/run_owner_mirror_tests.sh
#
# WHY THIS EXISTS. `signOut()` cleared the credentials and left all five
# device-local owner mirrors on disk. The second person to open a handed-on
# phone — and cable install is the only way this app gets onto a device, so
# that is the normal case — was met at the door by the FIRST person's email
# address under the words "Welcome back.", read their first name in the tour,
# and reached the number beat with their phone number already wearing the tick
# that means "that's you". The next thing that would have happened is the new
# account's confirmation texts arriving on the old owner's handset.
#
# The correct list already existed, in `forgetMeOnThisPhone` in SettingsView,
# and had done for months. Two lists, one of them silently empty, and nothing
# in this repo could see the difference — which is why the fix is a type that
# names the keys once and a gate that reads the source, rather than five more
# assignments that the sixth owner field will not be added to either.
#
# A source scan, like run_theme_contract_tests.sh, and for the same reason: the
# defect is the EXISTENCE of a second copy of a list, which no runtime
# assertion can see. The scanner itself is checked against fixtures first, both
# the shape that should pass and each drift that must not, so it cannot join
# the six can't-fail tests found in this tree this week by matching nothing.
#
# Exit code is the result. Non-zero means the two lists have drifted apart, or
# the read that puts a true number back has gone.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

session="$app/AnticipyApp.swift"
backend="$app/Backend/AnticipyBackend.swift"
settings="$app/Views/SettingsProfileView.swift"
for f in "$session" "$backend" "$settings"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# THE LIST IS NOT ALLOWED TO EXIST TWICE. Settings' "Forget me on this phone"
# is the other place the five mirrors are named; it predates OwnerMirror and
# still writes them out one by one. That is where this whole class of bug came
# from, so the gate says so out loud rather than letting the second copy pass
# unremarked — but it is a WARNING, not a failure: SettingsView belongs to
# another change, and a gate that goes red over a file this one may not touch
# is a gate somebody turns off.
forget=$(awk '/private func forgetMeOnThisPhone/,/^    }$/' \
    "$app/Views/SettingsView.swift" 2>/dev/null \
    | grep -c 'session\.owner[A-Za-z]* = ""' || true)
if [ "${forget:-0}" -gt 0 ]; then
    echo "note: forgetMeOnThisPhone still clears $forget owner mirrors by hand."
    echo "      OwnerMirror.clear() is the same list; until Settings calls it,"
    echo "      a sixth mirror has to be remembered in two places."
fi

# AND A THIRD COPY, in a file this change may not touch either. The recognizer
# is handed the owner's name by AnticipyVocabulary, which reads
# "ownerFirstName" and "ownerLastName" out of UserDefaults as literal strings.
# Renaming a key in OwnerMirror leaves that reading nothing, and the only
# symptom is the app getting quietly worse at hearing the person's own name —
# so it is said out loud here rather than left for somebody to find. A note for
# the same reason as the one above: the scanner reads two files, and this is
# the part of the list it cannot see.
vocab="$app/Audio/AnticipyVocabulary.swift"
copies=$(grep -oE '"owner(First|Last)Name"' "$vocab" 2>/dev/null | wc -l | tr -d ' ')
if [ "${copies:-0}" -gt 0 ]; then
    echo "note: AnticipyVocabulary names $copies owner keys as literal strings."
    echo "      Renaming one in OwnerMirror is silent there."
fi

# Compile the REAL pure replacement and profile-precedence policies beside the
# scanner tests. The lifecycle cases below therefore execute production code,
# including the crucial distinction between a missing profile value (nil) and
# an explicit empty one ("").
awk '/^enum OwnerMirror \{/,/^\}/' "$session" > "$out/owner_mirror.swift"
awk '/^enum PendingSpeechRetention \{/,/^\}/' "$session" > "$out/pending_retention.swift"
awk '/^enum AccountDeletionPolicy \{/,/^\}/' "$session" > "$out/account_deletion.swift"
awk '/^enum ActionWritePolicy \{/,/^\}/' "$session" > "$out/action_write.swift"
awk '/^enum OwnerProfileCanonical \{/,/^\}/' "$backend" > "$out/profile_canonical.swift"
awk '/^enum AgentUnpairPolicy \{/,/^\}/' "$backend" > "$out/agent_unpair.swift"
if ! grep -q 'struct Values' "$out/owner_mirror.swift" \
   || ! grep -q 'afterDeviceForget' "$out/pending_retention.swift" \
   || ! grep -q 'static func bounded' "$out/pending_retention.swift" \
   || ! grep -q 'static func outcome' "$out/account_deletion.swift" \
   || ! grep -q 'static func reconcile' "$out/action_write.swift" \
   || ! grep -q 'static func value' "$out/profile_canonical.swift" \
   || ! grep -q 'static func succeeded' "$out/agent_unpair.swift"; then
    echo "could not extract owner/profile/unpair production policies"
    exit 2
fi
{
    echo 'import Foundation'
    cat "$out/owner_mirror.swift"
    cat "$out/pending_retention.swift"
    cat "$out/account_deletion.swift"
    cat "$out/action_write.swift"
    cat "$out/profile_canonical.swift"
    cat "$out/agent_unpair.swift"
    sed '1{/^import Foundation$/d;}' "$here/OwnerMirrorTests.swift"
} > "$out/main.swift"

swiftc -O "$out/main.swift" -o "$out/ownermirrortests"
"$out/ownermirrortests" "$session" "$backend" "$settings"
