#!/bin/sh
# Compile the real view property without requiring a SwiftUI runtime.
set -eu
sh -n "$0"
case "${1:-}" in ''|--check-mutations) ;; *) echo 'unknown option'; exit 2;; esac
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
awk '
    BEGIN { print "extension ExecutionSurfaceFixture {" }
    !inside && /var executionSurfaceLabel: String \{/ { inside = 1; found = 1 }
    inside {
        print
        depth += gsub(/{/, "{"); depth -= gsub(/}/, "}")
        if (depth == 0) { closed = 1; exit }
    }
    END { print "}"; if (!found || !closed) exit 2 }
' "$app/Views/ContentView.swift" > "$out/Surface.swift"
cp "$here/ExecutionSurfaceLabelTests.swift" "$out/main.swift"
compile() {
    swiftc -O "$app/Backend/CalendarHandPolicy.swift" "$1" "$out/main.swift" -o "$out/test"
}
compile "$out/Surface.swift"
"$out/test"
if [ "${1:-}" = --check-mutations ]; then
    sed '/case "api":/d' "$out/Surface.swift" > "$out/NoAPI.swift"
    compile "$out/NoAPI.swift"
    if "$out/test" > "$out/mutant.log" 2>&1; then
        echo 'SURVIVED: API lane fell through to Browser'; exit 1
    fi
    echo 'KILLED: API lane fell through to Browser'
fi
