"""The app's extension-version pin must equal the version the extension ships.

`AnticipySession.expectedExtensionVersion` is the only number the stale-extension
banner compares against, and `staleExtension()` speaks only when Chrome reports a
version BEHIND it. So a pin left in the past does not produce a wrong banner --
it produces no banner at all, for everyone, forever, which is indistinguishable
from a fleet that is perfectly up to date.

On 2026-08-24 the pin was found reading 0.8.3 while extension/manifest.json read
0.11.0: three minor versions of drift, hand-maintained, unnoticed. Everyone on
0.8.3 through 0.10.x was told nothing while the backend served 0.11.0. This is
the second time stale extension bytes have cost a retest cycle -- the first was
0.3.3 live against 0.3.9 in source, which is why the banner exists at all.

The number lives in three files (manifest, app, and the Swift test that mirrors
the app's comparison). Three hand-copied values with no guard is how the drift
happened. This test is the guard.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "extension/manifest.json"
APP = ROOT / "app/ios/Anticipy/AnticipyApp.swift"
MIRROR = ROOT / "app/ios/Tests/StaleExtensionTests.swift"
BANNER = ROOT / "app/ios/Anticipy/Views/ContentView.swift"


def _shipped_version() -> str:
    version = json.loads(MANIFEST.read_text())["version"]
    assert isinstance(version, str) and version, \
        "extension/manifest.json has no usable version string"
    return version


def _swift_literal(path: Path, pattern: str) -> str:
    # re.M so the top-level `let expected` can be anchored to a line start and
    # never match a lookalike inside a longer expression.
    hit = re.search(pattern, path.read_text(), re.M)
    assert hit, (
        f"{path.relative_to(ROOT)} no longer declares the version literal this "
        f"test pins (looked for /{pattern}/). If the constant was renamed or "
        f"moved, update this test with it -- do not delete it, the pin rots "
        f"silently without it."
    )
    return hit.group(1)


def test_the_app_pin_matches_the_shipped_extension():
    shipped = _shipped_version()
    pinned = _swift_literal(
        APP, r'static let expectedExtensionVersion = "([^"]+)"')
    assert pinned == shipped, (
        f"extension/manifest.json ships {shipped} but "
        f"app/ios/Anticipy/AnticipyApp.swift pins {pinned}. Set "
        f'expectedExtensionVersion = "{shipped}" in AnticipyApp.swift (and the '
        f"`expected` mirror in app/ios/Tests/StaleExtensionTests.swift). Until "
        f"they match, the stale-extension banner cannot fire for anyone running "
        f"{pinned} or newer."
    )


def test_the_swift_test_mirror_matches_the_app_pin():
    shipped = _shipped_version()
    mirrored = _swift_literal(MIRROR, r'^let expected = "([^"]+)"')
    assert mirrored == shipped, (
        f"app/ios/Tests/StaleExtensionTests.swift mirrors the pin as {mirrored} "
        f"but extension/manifest.json ships {shipped}. Set "
        f'let expected = "{shipped}" in StaleExtensionTests.swift. A mirror that '
        f"disagrees with the app tests a comparison the app never makes."
    )


def test_the_pinned_version_is_comparable_the_way_swift_compares_it():
    """`staleExtension` maps each dotted component through `Int($0) ?? 0`, so a
    pin like "0.11.0-rc1" silently becomes 0.0.0 and can never be behind
    anything. Same silence, different cause."""
    pinned = _swift_literal(
        APP, r'static let expectedExtensionVersion = "([^"]+)"')
    assert re.fullmatch(r"\d+(\.\d+)*", pinned), (
        f"expectedExtensionVersion is {pinned!r}. Swift parses each component "
        f"with `Int($0) ?? 0`, so any non-numeric component reads as 0 and the "
        f"pin can never fire. Keep it plain dotted digits."
    )


def _banner_fragments() -> list:
    """The literal fragments the stale-extension banner concatenates."""
    src = BANNER.read_text()
    start = src.index("if let stale = session.staleExtensionVersion {")
    body = src[start:src.index(".font(", start)]
    # The comment above the Text() quotes the old fused string on purpose, so
    # strip prose before scanning or this test finds the bug it is describing.
    code = "\n".join(line for line in body.splitlines()
                     if not line.strip().startswith("//"))
    fragments = re.findall(r'"([^"]*)"', code)
    assert len(fragments) >= 2, (
        "the stale-extension banner in ContentView.swift no longer looks like "
        "concatenated literals. If it was rewritten, re-point this test at it -- "
        "the seam is only invisible while the banner cannot fire."
    )
    return fragments


def test_the_stale_banner_fragments_still_join_into_sentences():
    """The banner shipped reading "press Reload to get 0.11.0until then it's
    working from old instructions." for three minor versions, because the pin
    above had rotted the banner shut: an unreachable string never gets
    proofread by using the product. Fixing the pin is what exposed it, so the
    seam gets a guard rather than another pair of eyes."""
    fragments = _banner_fragments()
    for i, fragment in enumerate(fragments[:-1]):
        following = fragments[i + 1]
        assert fragment.endswith(" ") or following.startswith(" "), (
            f"app/ios/Anticipy/Views/ContentView.swift fuses two banner "
            f"fragments: ...{fragment[-28:]!r} runs straight into "
            f"{following[:28]!r}. End the earlier fragment with a space (after "
            f"its full stop) so the sentence break lives with the sentence that "
            f"owns it."
        )


def test_the_banner_still_names_the_version_it_wants():
    """"Reload to get the new one" is not an instruction anybody can check."""
    joined = "".join(_banner_fragments())
    assert "expectedExtensionVersion" in joined, (
        "the stale-extension banner in ContentView.swift stopped naming "
        "AnticipySession.expectedExtensionVersion, so it now tells someone to "
        "reload without saying what they should end up on."
    )
