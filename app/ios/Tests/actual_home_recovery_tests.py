from pathlib import Path

app = Path(__file__).resolve().parent.parent / "Anticipy"


def body(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise AssertionError(f"unclosed {signature}")


home = (app / "Views/ContentView.swift").read_text()
dashboard = (app / "Views/ConversationDashboard.swift").read_text()
settings = (app / "Views/SettingsAccessView.swift").read_text()
source = body(settings, "struct SettingsSourceView:")
render = body(dashboard, "private func view(for turn:")
construction = home[home.index("ConversationDashboard("):home.index(".accessibilityLabel(\"Settings\")")]
checks = {
    "actual Home injects existing task stop card":
        "} working:" in construction and "HandlingCard(job: job)" in construction,
    "actual Home injects existing event reply card":
        "} question:" in construction and "AskCard(event: event)" in construction,
    "synthetic work without a job keeps a prose fallback":
        "WorkingTurn(text: text)" in construction,
    "historical questions keep prose, not fresh approval":
        "QuestionTurn(text: text)" in construction,
    "thread calls working and question slots with identity":
        "working(id, text)" in render and "question(id, text)" in render,
    "capture detail uses the same interactive renderer":
        "view(for: turn)" in dashboard[dashboard.index(".sheet(item: $expandedTurn)"):],
    "actual source Settings constructs reopen control":
        'ActionRow("Allow Anticipy to ask again"' in source,
    "reopen changes only ask permission, not read permission":
        "ContextGrants().reopen(source)" in source
        and "grantContext(" not in source
        and "ContextGrants().grant(" not in source,
    "source Settings initializes and displays explicit declined state":
        "declined = ContextGrants().declined(source)" in source and "if declined" in source,
    "API tasks have their own structural status branch":
        'normalizedLane == "api"' in body(home, "struct HandlingCard:")
        and "Connected app is working" in home,
    "API tasks do not receive Chrome recovery instructions":
        'lane != "api"' in body(home, "private var browserHandling:"),
    "actual composer acknowledges synchronous persistence":
        "onSend: { line in session.acceptTyped(line) }" in construction
        and "guard onSend(line) else" in body(dashboard, "private func send()"),
    "new interactive cards inherit the existing root session":
        ".environmentObject(session)" in (app / "AnticipyApp.swift").read_text()
        and "@EnvironmentObject private var session: AnticipySession" in body(home, "struct HandlingCard:")
        and "@EnvironmentObject var session: AnticipySession" in body(home, "struct AskCard:"),
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
assert all(checks.values()), f"{sum(not value for value in checks.values())} actual-screen contract failures"
