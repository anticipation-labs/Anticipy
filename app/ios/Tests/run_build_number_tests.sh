#!/bin/sh
# Which build is the tester holding?
#
#   sh app/ios/Tests/run_build_number_tests.sh
#
# CURRENT_PROJECT_VERSION sat at 76 across NINETEEN iOS commits. Seven different
# source trees all called themselves build 76, so "is the bug still there in the
# build on my phone?" had no answer, and two research passes hit that as a real
# obstacle in one night. App Store Connect refuses a re-used build number, which
# is the only reason this was ever noticed before — and it is noticed at upload,
# days after the tree it should have described.
#
# Three legs, each anchored on something that MOVES:
#
#   1. the number is a number at all;
#   2. project.yml and the generated Xcode project agree — the build reads the
#      pbxproj, so a bump nobody ran `xcodegen generate` after ships the old
#      number while the repo swears it shipped the new one;
#   3. the iOS SOURCE has not moved since the number last did.
#
# Leg 3 is the one with teeth, and it is deliberately not "bump on every
# commit". It compares the working tree against the commit where the number last
# changed: bump it and the leg is green until the next source edit, which is
# exactly the rule a human would state.
#
# Exit code is the result. Non-zero means the number no longer identifies the
# bytes.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
ios=$(cd "$here/.." && pwd)
yml="$ios/project.yml"
pbx="$ios/Anticipy.xcodeproj/project.pbxproj"
[ -f "$yml" ] || { echo "missing $yml"; exit 2; }

version=$(grep -E '^[[:space:]]*CURRENT_PROJECT_VERSION:' "$yml" \
    | head -1 | sed 's/.*"\(.*\)".*/\1/')
case "$version" in
    ''|*[!0-9]*)
        echo "CURRENT_PROJECT_VERSION in project.yml is not a plain integer:"
        echo "  '$version'"
        echo "App Store Connect compares build numbers as numbers, and every"
        echo "check below reads this one. A value this script cannot read is a"
        echo "check that reports on nothing."
        exit 2
        ;;
esac

# ---------------------------------------------------------- 2. the generated
# THE BUILD READS THE PBXPROJ. project.yml is the source of truth only if
# somebody ran xcodegen; the .xcodeproj is committed, so a bump that skipped
# that step ships the old number under a repo that says otherwise — the same
# shape as the 2026-08-15 failure where a literal in the Info.plist silently
# overwrote the setting and build 54 shipped twice while the repo claimed 55
# and 56.
if [ -f "$pbx" ]; then
    mismatched=$(grep -o 'CURRENT_PROJECT_VERSION = [^;]*;' "$pbx" \
        | sed 's/CURRENT_PROJECT_VERSION = //; s/;//' | sort -u \
        | grep -vx "$version" || true)
    if [ -n "$mismatched" ]; then
        echo "project.yml says build $version and the generated Xcode project says:"
        printf '  %s\n' $mismatched
        echo ""
        echo "xcodebuild reads the pbxproj, so the app on the phone would carry"
        echo "the other number. Run: cd app/ios && xcodegen generate"
        exit 2
    fi
fi

# And the Info.plist must keep DERIVING the number rather than restating it.
plist="$ios/Anticipy/Info.plist"
if [ -f "$plist" ] \
    && ! grep -q '\$(CURRENT_PROJECT_VERSION)' "$plist"; then
    echo "Info.plist no longer references \$(CURRENT_PROJECT_VERSION)."
    echo "A literal there overwrites the build setting silently: that is how"
    echo "build 54 shipped twice on 2026-08-15 while the repo claimed 55 and 56."
    exit 2
fi

# ------------------------------------------------------------- 3. it moves
if ! command -v git >/dev/null 2>&1 \
    || ! git -C "$here" rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "This check needs the repository's history to run, and cannot see it."
    echo "The rule below is 'the build number has moved since the iOS source"
    echo "did', and there is no way to answer that from a tree alone. Reporting"
    echo "nothing here would be the third gate rule this week that passed by"
    echo "matching nothing."
    exit 2
fi
root=$(git -C "$here" rev-parse --show-toplevel)
rel_yml=${yml#"$root"/}
rel_src=${ios#"$root"/}/Anticipy

# The commit where the number itself last changed. `-G` matches the DIFF, so a
# commit that only reworded the comments around the setting is not one of these.
bump=$(git -C "$root" log -1 --format=%H -G'CURRENT_PROJECT_VERSION: "' -- "$rel_yml")
if [ -z "$bump" ]; then
    echo "No commit in this history ever changed CURRENT_PROJECT_VERSION."
    echo "That is either a shallow clone, or a branch where the number has never"
    echo "moved at all — and the second one is the failure this leg is for."
    echo "An empty search is not a pass."
    exit 2
fi
was=$(git -C "$root" show "$bump:$rel_yml" \
    | grep -E '^[[:space:]]*CURRENT_PROJECT_VERSION:' \
    | head -1 | sed 's/.*"\(.*\)".*/\1/')

# Already moved since that commit — the bump is sitting in the working tree,
# uncommitted, which is exactly where it should be while the change that earned
# it is still being written.
#
# AN INCREASE, NOT MERELY A DIFFERENCE. This tested `!=`, so 79 in the working
# tree against a history that had reached 80 printed "bumped from 80 and not yet
# committed" and exited 0 — a DOWNGRADE reported as a bump. It is not exotic:
# a revert, a rebase, a merge that took the older project.yml, or a second
# worktree all produce it, AND THIS REPO HAS TWO WORKTREES ON DIVERGENT
# LINEAGES. Two different apps would then call themselves build 79, which is
# the exact condition this whole leg exists to prevent, reached through the
# branch meant to say the condition was handled.
#
# Compared as INTEGERS. `[ "$version" -gt "$was" ]` on a non-numeric value is a
# shell error, not a pass, and `set -e` at the top of this file makes that a
# red leg — which is the right answer for a version nobody can order.
case "$version$was" in
    *[!0-9]*)
        echo "CURRENT_PROJECT_VERSION is not a plain integer:"
        echo "  working tree: $version"
        echo "  last bumped:  $was"
        echo ""
        echo "This leg has to ORDER two build numbers to tell a bump from a"
        echo "downgrade, and it cannot order these. Whatever the scheme is, it"
        echo "is not one this check can vouch for."
        exit 2
        ;;
esac
if [ "$version" -gt "$was" ]; then
    echo "build $version, bumped from $was and not yet committed"
    exit 0
fi
if [ "$version" -lt "$was" ]; then
    echo "The build number has gone BACKWARDS: $was in history, $version here."
    echo ""
    echo "This is what a revert, a rebase, or a merge that took the older"
    echo "project.yml leaves behind — and with two worktrees on divergent"
    echo "lineages it is the ordinary accident, not the exotic one. Build $was"
    echo "already exists and is not these bytes, so 'which build are you"
    echo "holding' stops having an answer exactly as it did when nineteen"
    echo "commits shipped as build 76."
    echo ""
    echo "Set CURRENT_PROJECT_VERSION above $was in app/ios/project.yml, say in"
    echo "its comment what changed, then run:"
    echo "  cd app/ios && xcodegen generate"
    exit 2
fi

# `git diff <commit> -- path` compares the WORKING TREE against that commit, so
# an uncommitted source edit counts. That is the point: the number has to be
# right before the commit lands, not after somebody notices at upload.
if ! git -C "$root" diff --quiet "$bump" -- "$rel_src"; then
    echo "The iOS source has changed since build $version was set, and the build"
    echo "number has not moved:"
    git -C "$root" diff --stat "$bump" -- "$rel_src" | tail -12
    echo ""
    echo "Two different apps would call themselves build $version. That is how"
    echo "nineteen commits shipped as build 76 and 'which build are you holding'"
    echo "stopped having an answer. Bump CURRENT_PROJECT_VERSION in"
    echo "app/ios/project.yml, say in its comment what changed, then run:"
    echo "  cd app/ios && xcodegen generate"
    exit 2
fi

echo "build $version, and the iOS source has not moved since it was set"
