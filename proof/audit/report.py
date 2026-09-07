"""Build the dated audit checkpoint PDF from repository and local evidence."""
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
people = json.loads((ROOT / "proof/audit/corpus/people.json").read_text())["people"]
para("ANTICIPY", "Title")
para("Engineering audit checkpoint<br/>7 September 2026", "Heading1")
para("<b>Release status: not ready for a verified fresh-user phone test.</b> The Mac environment is ready. Local repairs and evidence exist. Production deployment, comprehensive execution coverage and complete account erasure remain unfinished.")
para("This checkpoint responds to the owner's request to stop scope expansion and deliver quickly. It is an honest record of completed measurements and remaining work, not a claim of perfection or a completed every-route audit.")
heading("What is ready")
para("The source-of-record checkout is <b>/Users/omarebrahim/Anticipy</b>, branch <b>cloudflare-backend</b>. The unrelated main branch was not used. Node 24, Python 3.11, Xcode and an unsigned iPhone simulator build were prepared. The isolated Cloudflare API runs on localhost:8787; deterministic browser fixtures run on localhost:8899. Production keys are excluded from the local app environment.")
para("Before code changes, all 63 iOS suites passed. The app source is version 1.1.1, build 158; no iOS source was changed in this audit. The simulator build succeeded. No laptop signing or upload was attempted.")
para("Final local checks: <b>2,986 Python tests passed, two skipped; all 34 chained Worker test files passed; API and brain TypeScript checks passed.</b> The erasure suite now has 15 passing cases. Real-model transcripts exercised 14 distinct fictional people; the three reply failures were repeated through the complete local ingestion/brain path. These checks do not certify every route or live integration.")
heading("What Anticipy does")
para("Anticipy is a contextual personal assistant. Speech or typed input becomes an account-scoped API event. The brain retrieves memory, interprets the conversation, asks for missing information, and creates work. Browser, connected-app API, research or device executors perform the work. Results and evidence return to the app. Permissions and persisted receipts must govern real effects; a reassuring sentence is not proof of completion.")
para(f"Paid audit model usage recorded at generation: <b>US${spend.get('observed_cost_usd',0):.3f}</b>. Charged plus unresolved reservations: <b>US${spend.get('committed_estimate_usd',0):.3f}</b>. Owner-authorized maximum: US$50; the model proxy uses a lower US$25 operating ceiling. Research itself used no paid API calls.")
page()
heading("Repairs and evidence")
items = [
 ("Account deletion", "Local tests reproduced omitted connection/reset records, cross-account deletion through a claimed legacy ID, and generic DELETE bypassing cleanup. The handler now enumerates 15 owned tables, respects canonical identity, cleans provider/evidence handles first, and durably schedules memory purge."),
 ("Late writes during deletion", "A late evidence write and post-deletion transcript insertion were reproduced. A new SQL migration fences writes using the durable purge record. The handler refuses cleanup when that migration is absent. Production application and late external OAuth effects remain unverified."),
 ("Connections", "Provider pagination now checks every page and owner. Conditional permission updates cannot resurrect a deleted connection or overwrite a newer expiration state. Real catalogs returned 335 tools across Calendar, Gmail, Notion and Slack; this does not prove authenticated execution."),
 ("Memory durability", "A lock spans snapshot copy and upload so an older snapshot cannot win within one process. Restore stages and validates SQLite plus clock JSON before publishing either. Cross-container fencing and atomic remote generations remain open."),
 ("Authentication and input", "Malformed JWT signatures now refuse authentication instead of returning 500. Known required/unique constraints return validation errors. Anonymous account creation cannot choose its canonical ID. The local 131-request unauthenticated route sweep returned no 500 after repair; it is not happy-path coverage."),
 ("Grounded interpretation and replies", "A timezone no longer asserts a city. The no-key intent-pattern fallback was deleted. Reply composition now receives persisted job state, explicit result evidence and related memory. Two replay rounds preserved failures; the second set of 15 replies had no unsupported identities or completion claims on manual review."),
 ("CI", "The proposed iOS workflow compiles the committed project for the simulator on ordinary pushes. Apple upload remains explicitly gated. CI execution of the audit changes is still required."),
]
for title, body in items:
    para(f"<b>{title}.</b> {body}")
para("Evidence: research/audit-2026-09-06/FINDINGS.md, voice-replay-evidence.json, inventory/; proof/audit/; new regression tests under tests/ and migration/workers/test/. Private traces, account identifiers, credentials and spend records remain in ignored work/audit/. All repairs are local until verified against deployment.")
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
heading("What prevents a phone release")
para("The 365-document and route inventories are not fully reviewed. Fifty fictional people and 101 contacts are authored, but complete browser/provider outcomes for all fifty are not demonstrated. Standing intent heuristics remain. Live Composio execution and controlled SMS delivery remain unverified. Shared legacy backups require selective erasure without affecting other people. Local repairs need adversarial deployment checks. Only then can the authorized owner reset and CI/TestFlight release be completed and checked against App Store Connect.")
page()
heading("50 fictional user exemplars")
para("Each case has a private simulated identity, contacts, history and an evaluator-only outcome. These are authored test cases, not fifty successful executions. Ten held-out cases remain excluded from development tuning.")
for i,p in enumerate(people):
    if i and i % 6 == 0:
        page(); heading(f"User exemplars {i+1}-{min(i+6,50)}")
    para(f"<b>{i+1}. {escape(p['name'])} - {escape(p['occupation'])}, {escape(p['city'])}</b><br/>"
         f"Task: {escape(p['transcript']['text'])}<br/>"
         f"Expected: {escape(p['evaluator_only']['required_outcome'])}", "CaseAudit")

def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#DCE4ED")); canvas.line(48,42,564,42)
    canvas.setFont("Helvetica",8);canvas.setFillColor(colors.HexColor("#52657B"))
    canvas.drawString(48,29,"ANTICIPY / AUDIT CHECKPOINT / LOCAL EVIDENCE")
    canvas.drawRightString(564,29,str(doc.page))

SimpleDocTemplate(str(OUT), pagesize=(612,792), rightMargin=48,leftMargin=48,topMargin=45,bottomMargin=56,
                  title="Anticipy engineering audit checkpoint",author="Anticipy engineering").build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
