"""Build the dated audit report from repository and local evidence."""
from pathlib import Path
import json
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/pdf/Anticipy-audit-2026-09-07.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyAudit", fontName="Helvetica", fontSize=10, leading=14, spaceAfter=9, textColor=colors.HexColor("#243248")))
styles.add(ParagraphStyle(name="CaseAudit", fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=13))
styles["Title"].textColor = colors.HexColor("#122846")
styles["Heading1"].textColor = colors.HexColor("#122846")
story = []

def para(text, style="BodyAudit"):
    story.append(Paragraph(text, styles[style]))

def heading(text):
    para(text, "Heading1")

def page():
    story.append(PageBreak())

spend = json.loads((ROOT / "work/audit/spend.json").read_text())
verification = json.loads((ROOT / "research/audit-2026-09-06/verification.json").read_text())
people = json.loads((ROOT / "proof/audit/corpus/people.json").read_text())["people"]
para("ANTICIPY", "Title")
para("Engineering audit<br/>7 September 2026", "Heading1")
para("<b>Fresh-user test: preparation remains incomplete.</b> The API repairs are deployed and verified. The current iOS source is already available in TestFlight build 159. Live Google consent and complete account erasure remain unfinished.")
para("This report distinguishes measured outcomes from remaining coverage. All 50 people have real-model transcript observations; five browser simulations have verified results. Neither measurement certifies every external integration or every possible task.")
heading("What is ready")
para("The source-of-record checkout is <b>/Users/omarebrahim/Anticipy</b>, branch <b>cloudflare-backend</b>. The unrelated main branch was not used. Node 24, Python 3.11, Xcode and an unsigned iPhone simulator build were prepared. The isolated Cloudflare API is configured for localhost:8787 and deterministic browser fixtures for localhost:8899. Production keys are excluded from the local app environment.")
para("Before code changes, all 63 iOS suites passed. No iOS source was changed in this audit. The simulator build succeeded. App Store Connect independently confirms build 159 is VALID and IN_BETA_TESTING. Its complete app/ios tree matches this checkout. The existing CI upload allocated 159 from source metadata 158. No laptop signing or redundant upload was attempted.")
para("<b>Final CI: 3,017 Python checks passed, seven skipped; all 35 Worker test files and type checks passed.</b> Account erasure has 17 local cases and connection authentication has 61. The deployed API passed 29 live checks, including isolated account creation, ownership refusal and both account-erasure paths. These checks do not certify every route or live integration.")
para("<b>Brain runtime:</b> " + escape(verification.get("brain_live_summary", "Deployment verification is still in progress. Old runtime images have not all been replaced.")))
para("The browser runner now executes eight isolated suites concurrently. All <b>94 suites passed locally in 72.51 seconds and in CI in 73 seconds</b>. The prior CI browser step took 458 seconds: the new runner is about 6.3 times faster on CI. A deliberate child-process failure made the runner fail while the other suites still completed; coverage and failure checks were retained.")
heading("What Anticipy does")
para("Anticipy is a contextual personal assistant. Speech or typed input becomes an account-scoped API event. The brain retrieves memory, interprets the conversation, asks for missing information, and creates work. Browser, connected-app API, research or device executors perform the work. Results and evidence return to the app. Permissions and persisted receipts must govern real effects; a reassuring sentence is not proof of completion.")
para(f"Paid audit model usage recorded at generation: <b>US${spend.get('observed_cost_usd',0):.3f}</b>. Charged plus unresolved reservations: <b>US${spend.get('committed_estimate_usd',0):.3f}</b>. Owner-authorized maximum: US$50; the model proxy uses a lower US$25 operating ceiling. Research itself used no paid API calls.")
page()
heading("Repairs and evidence")
items = [
 ("Account deletion", "Local tests reproduced omitted connection/reset records, cross-account deletion through a claimed legacy ID, and generic DELETE bypassing cleanup. The handler now enumerates 15 owned tables, respects canonical identity, cleans provider/evidence handles first, and durably schedules memory purge."),
 ("Late writes during deletion", "A late evidence write and post-deletion transcript insertion were reproduced. All 32 SQL write-fence triggers are installed live. Initial live deletion exposed a production schema difference missing from fixtures; writes now use the actual ledger columns, with a regression against that shape. Late external OAuth effects remain unverified."),
 ("Connections", "Provider pagination now checks every page and owner. Conditional permission updates cannot resurrect a deleted connection or overwrite a newer expiration state. Real catalogs returned 335 tools across Calendar, Gmail, Notion and Slack; this does not prove authenticated execution."),
 ("Memory durability", "A lock spans snapshot copy and upload so an older snapshot cannot win within one process. Restore stages and validates SQLite plus clock JSON before publishing either. Runtime health now measures the child process, source fingerprint and snapshot age. Cross-container fencing and atomic remote generations remain open."),
 ("Authentication and input", "Malformed JWT signatures now refuse authentication instead of returning 500. Known required/unique constraints return validation errors. Anonymous account creation cannot choose its canonical ID. The local 131-request unauthenticated route sweep returned no 500 after repair; it is not happy-path coverage."),
 ("Grounded interpretation and replies", "A timezone no longer asserts a city. The no-key intent-pattern fallback was deleted. Replies receive persisted job state and evidence. Both model tiers receive canonical owner identity; two full-path replays stopped substituting the owner for an unknown client or pickup contact. The queued-work reply defect found in held-out testing was then repaired and verified in twelve real-model reply checks."),
 ("Connection screen", "The owner supplied actual SMS delivery evidence. The deployed code screen now explains phone verification before account connection, labels the six-digit input, and avoids automatic focus that opened a password popup. Google consent is still outstanding."),
 ("CI", "Ordinary iOS pushes now build the committed project for the simulator. Apple upload remains explicitly gated. API deployment verifies the active revision and behavior. Brain deployment additionally verifies running images and current snapshots; a successful upload alone cannot pass it."),
]
for title, body in items:
    para(f"<b>{title}.</b> {body}")
para("Evidence: research/audit-2026-09-06/FINDINGS.md, verification.json, held-out-results.json, browser-simulation-results.json, voice-replay-evidence.json, inventory/; proof/audit/; regression tests under tests/ and migration/workers/test/. Private traces, account identifiers, credentials and spend records remain in ignored work/audit/. Individual evidence records identify local, simulated and live scope.")
page()
heading("Harness and memory research")
para("A harness is the software around the model: context assembly, tool execution, access boundaries, durable state, retries, progress reporting and evaluation. Workflows prescribe a path; agents choose actions based on context. Generality requires unfamiliar task combinations, not many renamed versions of one example.")
para("Good evaluation inspects persisted outcomes independently of the agent's prose. It includes missing context, ambiguity, hostile content, revoked permissions, duplicate delivery, response loss after a successful write, restart, correction and erasure. Development and held-out cases must stay separate. A simulated integration proves orchestration only; a real provider receipt and handset observation establish different facts.")
para("Memory has distinct roles: working context, episodes, consolidated facts and procedures. Correct retrieval does not prove accurate interpretation, fresh facts, ownership isolation, erasure or crash durability. Derived summaries need provenance so corrections and deletions reach them too.")
for title, url in [
 ("Anthropic: Building effective agents", "https://www.anthropic.com/engineering/building-effective-agents"),
 ("OpenAI: Evaluation best practices", "https://developers.openai.com/api/docs/guides/evaluation-best-practices"),
 ("WebArena: stateful browser evaluation", "https://arxiv.org/abs/2307.13854"),
 ("Apple ToolSandbox: stateful multi-turn tool evaluation", "https://arxiv.org/html/2408.04682v1"),
 ("LongMemEval: long-term memory evaluation", "https://xiaowu0162.github.io/long-mem-eval/"),
 ("Cloudflare: R2 consistency", "https://developers.cloudflare.com/r2/reference/consistency/"),
 ("Composio: connected-account lifecycle", "https://docs.composio.dev/reference/api-reference/connected-accounts"),
]:
    para(f'<link href="{url}" color="#176880">{title}</link>')
para("The detailed primary-source ledger, dates, limitations and Anticipy-specific inferences are in RESEARCH.md. These sources guide the audit; they do not establish that Anticipy passed it.")
heading("Remaining work")
para("The 365-document and route inventories are not fully reviewed. Standing intent heuristics remain. The reproduced profile-memory merge, veto and completion defects are repaired and verified on the live runtime. Full browser/provider execution across all fifty people is not demonstrated. A fresh code reached the owner's phone, but Chrome blocked automation because an extension popup was open. Google consent and live connected-app execution remain unproven. Selective erasure must preserve other people's data in shared legacy archives. One historical PocketBase backup is corrupt. A separate recovery passes integrity checks, preserves all 112 schema objects and matches every row in 45 readable original tables; 489 agent records were recovered from the corrupt table and match an independently recovered backup from the prior day. Selective cleanup remains in progress. The product-account reset has not been performed.")
page()
heading("Memory and reply behavior")
para("Sixteen real-model memory cases now pass: different people and reversed relationships remain separate; changed values retire stale facts; equivalent notes merge; forgetting is scoped; and a completion cannot close a task for the wrong recipient. Initial default-model runs still failed identity/case changes. The stronger configured model passed the complete set and is now wired into these judgments. Unknown historical/veto comparisons defer writes; unknown task resolutions keep commitments open.")
para("Twelve real-model reply compositions were reviewed: three welcomes correctly name Anticipy, queued work is acknowledged without a repeated request to start, missing reminder content is requested without claiming the reminder exists, and running work is described as in progress. These were synthetic contexts; no messages were sent by the composer tests.")
heading("Measured task outcomes")
para("<b>Transcript lane:</b> all 50 fictional people and their authored contact/context histories ran through real-model ingestion. Forty development cases and ten held-out cases are recorded separately. The outcomes are persisted proposed or queued jobs, not completed external actions. Most jobs await confirmation; queued work still needs executor evidence.")
para("<b>Browser lane:</b> the shipped extension agent ran with real Claude Sonnet 4.6 responses, simulated pages and navigation, and an independent model reviewing evidence. Five read tasks completed: two-store price comparison; revised attendance versus room capacity; accepted gallery works versus waiting-list items; a success banner contradicted by the persisted ledger; and a document containing hostile instructions. The gallery case first stopped for mailbox consent and resumed only after a simulated owner reply. No real mailbox, Chrome session or external provider was used in this lane.")
para("<b>Live lane:</b> 29 API checks passed over api.anticipy.ai. Sendblue delivery is supported by the owner's Messages screenshot. Google Calendar consent and authenticated execution are still unconfirmed. App Store Connect query run 34084961603 confirms existing build 159 is available internally; installation on the owner's phone remains a handset check.")
para("<b>Erasure:</b> the new operator path checks canonical account ID, account email, profile email and phone before invoking the same cleanup used by public account deletion. Negative cases preserve unrelated accounts. The live positive check used only an isolated synthetic fixture. Historical archive inspection is read-only so far; no claim of a clean account is made.")
page()
heading("Spoken approval that respects context")
para("The backend used a phrase pattern to approve held work. It could treat agreement with a caller as permission for a task, select the newest task rather than the intended one, and treat an unreadable timestamp as freshly asked. That pattern has been removed.")
para("The configured strong model now answers one separate question: does this owner utterance authorize one identified task in its current scope? It receives the supplied conversation, speaker evidence, and held tasks including their corrections. Approved, refused, clarification and unknown are distinct outcomes. Only an unambiguous approved task can be released. Single-word yes and unfamiliar phrasing reach the same judgment.")
para("An approval is also tied to the exact stored task. The API provides a task ETag; the brain re-reads after the model and sends If-Match. The database itself refuses an amendment or cancellation race, even if the request passed earlier policy checks. A stale or repeated approval returns 412 and leaves the current record intact.")
heading("What was actually exercised")
para("<b>18 real model judgments:</b> five legitimate approvals, including French wording and explicit selection of an older task; thirteen cases that must remain held, including refusal, quotation, conditions, changed recipient, a caller's agreement, missing context and hostile source text. All passed and all provider calls returned.")
para("<b>18 complete local paths:</b> the same cases then ran through the production consent method, the real model, HTTP, workerd and SQLite. Exactly the five intended tasks became queued; the other thirteen cases left all tasks held. Every synthetic account was deleted afterward. No messages, bookings or external provider effects were executed.")
para("<b>Database and runtime:</b> fourteen SQLite checks exercised concurrent edits, cancellation, ownership changes, replay and invalid preconditions. The deployed production API passed 29 checks including fresh approval, stale refusal and repeated-approval refusal. Brain source and snapshot verification is recorded in verification.json and BACKEND-CONSENT-REPAIR.md.")
para("Evidence: spoken-consent-results.json, spoken-consent-wire-results.json, tests/test_spoken_yes_never_guesses.py, migration/workers/test/job-approval-race.test.ts, and the live release proofs in proof/audit/. Other legacy interpretation rules remain under review; this repair does not certify all agent decisions.")
page()
heading("50 fictional user exemplars")
para("Each case has a simulated identity, contacts, history and an evaluator-only outcome. Every case has a real-model transcript observation. The expected outcome below is the intended result, not a claim of completed external work. Ten held-out cases were observed only after development repairs and were not used for tuning.")
for i,p in enumerate(people):
    if i and i % 6 == 0:
        page(); heading(f"User exemplars {i+1}-{min(i+6,50)}")
    para(f"<b>{i+1}. {escape(p['name'])} - {escape(p['occupation'])}, {escape(p['city'])}</b><br/>"
         f"Task: {escape(p['transcript']['text'])}<br/>"
         f"Expected: {escape(p['evaluator_only']['required_outcome'])}", "CaseAudit")

def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#DCE4ED")); canvas.line(48,42,564,42)
    canvas.setFont("Helvetica",8);canvas.setFillColor(colors.HexColor("#52657B"))
    canvas.drawString(48,29,"ANTICIPY / ENGINEERING AUDIT / 7 SEPTEMBER 2026")
    canvas.drawRightString(564,29,str(doc.page))

SimpleDocTemplate(str(OUT), pagesize=(612,792), rightMargin=48,leftMargin=48,topMargin=45,bottomMargin=56,
                  title="Anticipy engineering audit",author="Anticipy engineering").build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
