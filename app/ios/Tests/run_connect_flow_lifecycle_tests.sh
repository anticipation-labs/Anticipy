#!/bin/sh
# Extract whole actual view methods; only private visibility and surrounding
# UI/property wrappers are replaced. Real ConnectSession/AccountWriteLease run.
set -eu
case "${1:-}" in ''|--check-mutations) ;; *) echo 'unknown option'; exit 2;; esac
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$app" "$out/FlowBodies.swift" <<'PY'
from pathlib import Path
import re, sys
app = Path(sys.argv[1])
def declaration(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == '{': depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0: return source[start:index + 1].removeprefix('private ')
    raise AssertionError('unterminated declaration: ' + signature)
settings = (app / 'Views/SettingsHomeView.swift').read_text()
onboarding = (app / 'Views/OnboardingView.swift').read_text()
root = (app / 'AnticipyApp.swift').read_text()
output = 'import Foundation\n' + declaration(root, 'enum AccountWriteLeasePolicy {')
output += '\n' + declaration(settings, 'struct ConnectFlow:')
for source, target, signatures in [
    (settings, 'SettingsFlowFixture', ['private func startConnect(', 'private func runConnect(']),
    (onboarding, 'OnboardingFlowFixture', ['private func startConnecting(', 'private func connectStepMovesOn()', 'private func runConnect(',
      'nonisolated static func sentences(']),
]:
    output += '\n@MainActor extension ' + target + ' {\n'
    for signature in signatures: output += declaration(source, signature) + '\n'
    # Optional solely so the old product source compiles for a behavioral RED.
    if 'private func connectFlowIsCurrent(' in source:
        output += declaration(source, 'private func connectFlowIsCurrent(') + '\n'
    if 'private func connectMovedToBackground()' in source:
        output += declaration(source, 'private func connectMovedToBackground()') + '\n'
        assert '.onChange(of: scenePhase)' in source
        assert 'if phase != .active { connectMovedToBackground() }' in source
    else:
        # Baseline view has no lifecycle callback: represent that absence,
        # allowing the real late-response behavior to fail the assertions.
        output += 'func connectMovedToBackground() {}\n'
    output += '}\n'
Path(sys.argv[2]).write_text(output)
mutations = {
    'flow_identity': (r'let id = UUID\(\)', 'var id: String { app.slug }', 1),
    'flow_lease': (r'AccountWriteLeasePolicy\.isCurrent\(flow\.lease,[\s\S]+?isSignedIn: session\.isSignedIn\)', 'true', 2),
    'catalog_generation': (r'connectSelectionID == selectionID', 'true', 1),
    'catalog_lease': (r'AccountWriteLeasePolicy\.isCurrent\(lease,[\s\S]+?isSignedIn: session\.isSignedIn\)', 'true', 1),
    'prompt_identity': (r'connect\.prompt\?\.attemptID == prompt\.attemptID', 'true', 2),
    # The SUCCESS sites and the CATCH sites are different expressions: the catch
    # compares the optional-bound local (`== attemptID`), so the regex above
    # never touched it and half the guard was advertised as proved and was not.
    # The two patterns cannot collide — `== attemptID` does not match at the
    # position of `== prompt.attemptID`.
    'catch_prompt_identity': (r'connect\.prompt\?\.attemptID == attemptID', 'true', 2),
    'background': (r'func connectMovedToBackground\(\) \{[\s\S]+?\n    \}', 'func connectMovedToBackground() {}', 2),
}
for name, (pattern, replacement, expected) in mutations.items():
    changed, count = re.subn(pattern, replacement, output)
    if count != expected: raise AssertionError(f'{name}: expected {expected} sites, got {count}')
    Path(sys.argv[2]).with_name(name + '.swift').write_text(changed)
PY
swiftc -O -parse-as-library "$app/Backend/ConnectHandoff.swift" \
    "$app/Backend/ConnectSession.swift" "$out/FlowBodies.swift" \
    "$here/ConnectFlowLifecycleTests.swift" -o "$out/test"
"$out/test"
if [ "${1:-}" = --check-mutations ]; then
    for mutation in flow_identity flow_lease catalog_generation catalog_lease prompt_identity catch_prompt_identity background; do
        swiftc -O -parse-as-library "$app/Backend/ConnectHandoff.swift" \
            "$app/Backend/ConnectSession.swift" "$out/$mutation.swift" \
            "$here/ConnectFlowLifecycleTests.swift" -o "$out/mutant"
        if "$out/mutant" > "$out/$mutation.log" 2>&1; then
            echo "SURVIVED: $mutation"; exit 1
        fi
        grep -q '^FAIL:' "$out/$mutation.log" || { echo "mutation did not fail behaviorally: $mutation"; exit 2; }
        echo "KILLED: $mutation"
    done
fi
