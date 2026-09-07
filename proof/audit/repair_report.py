"""Render the concise repair brief from recorded release state."""
import json
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/Anticipy-repair-brief-2026-09-07.pdf'
state=json.loads((ROOT/'research/overnight-2026-09-07/repair-live-release.json').read_text())
ink=colors.HexColor('#201d19');gold=colors.HexColor('#936d36');muted=colors.HexColor('#68645d')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleA',fontName='Times-Bold',fontSize=30,leading=33,textColor=ink,spaceAfter=17))
styles.add(ParagraphStyle(name='DeckA',fontName='Helvetica',fontSize=12,leading=18,textColor=muted,spaceAfter=18))
styles.add(ParagraphStyle(name='HeadA',fontName='Helvetica-Bold',fontSize=13,leading=18,textColor=gold,spaceBefore=14,spaceAfter=6))
styles.add(ParagraphStyle(name='BodyA',fontName='Helvetica',fontSize=10.5,leading=15,textColor=ink,spaceAfter=9))
styles.add(ParagraphStyle(name='SmallA',fontName='Helvetica',fontSize=9,leading=12,textColor=muted,spaceAfter=6))
def p(text,style='BodyA'):return Paragraph(text,styles[style])
def head(text):return p(text,'HeadA')
def footer(c,doc):
 c.setFillColor(colors.HexColor('#faf7f0'));c.rect(0,0,612,792,fill=1,stroke=0)
 c.setFillColor(gold);c.setFont('Helvetica-Bold',9);c.drawString(48,752,'ANTICIPY  /  ENGINEERING RECEIPT')
 c.setFillColor(muted);c.setFont('Helvetica',8);c.drawString(48,28,'07 September 2026  |  cloudflare-backend  |  '+state.get('final_revision','03f0c7f4')[:8]);c.drawRightString(564,28,str(doc.page))
story=[p('What was broken.<br/>What changed.','TitleA'),p(f'A repair brief for iOS build {state["ios_build"]} and browser extension 0.17.0. Every proof below names its limit.','DeckA')]
for title,body in [
 ('The browser missed its target','Smooth scrolling left click coordinates outside the visible page. The mapper now completes the scroll before measuring and refuses removed controls. Two real Chrome fixtures changed from zero clicks to exactly one each.'),
 ('One slow request held up the queue','Browser background requests now have a 20-second deadline, including stalled response bodies. Connection planning runs in one bounded HTTP thread so it cannot hold the brain\'s other work. No automatic replay of uncertain writes.'),
 ('Native calendar had no working hand','The phone now consumes approved native-calendar work through EventKit. Approval and release use separate conditional writes. Saving, retrying and undoing require actual calendar readback.'),
 ('An app reply did not mean a text','App and SMS replies now share a saved message and delivery queue. SendBlue gets one claimed attempt. The app shows queued, pending, delivered or unconfirmed using records for that exact message. A timeout is never called delivered.'),
 ('Discovery had evidence inputs nobody used','An hourly collector now reads recent owner conversation. A model identifies an app the owner actually uses; the live catalog verifies its identity. The existing consent and nudge policy decides whether an offer may follow.')]:
 story += [head(title),p(body)]
story += [p('Release state: '+state.get('release_summary','Backend/source and TestFlight verification are in progress.'),'SmallA'),PageBreak()]
story += [p('How the harness works.','TitleA'),p('You talk. It remembers the relevant context. It asks if it needs something. It does the approved work. It tells you what actually happened.','DeckA')]
for n,title,body in [
 ('01','Hear and save','The phone transcribes speech locally or sends your typed reply. SendBlue delivers incoming texts to the Worker. Both become owner-bound events in Cloudflare D1.'),
 ('02','Understand in context','The owner\'s brain reads the conversation, pending work and memory. Models decide meaning. Transport identities and schema checks prevent another person\'s data or a quoted instruction becoming your authorization.'),
 ('03','Choose a capable hand','Research, connected APIs, the browser extension and the new native calendar executor are different ways to do work. A missing account needs a connection offer; a missing fact needs a question. Connecting an account does not authorize every possible action.'),
 ('04','Approve, act, verify','The structured plan carries an owner, version, scope, approval and execution lease. A hand claims that plan and writes a receipt. If an external effect may already have happened, it is held for reconciliation instead of repeated.'),
 ('05','Answer through one conversation','The answer is persisted before its text-delivery attempt. A restart can deliver saved text without rerunning the task. SendBlue acceptance and handset delivery are different recorded facts.')]:
 story += [head(n+'  '+title),p(body)]
story += [head('A concrete example'),p('“My project briefs are in Quillbox. Read the latest one and prepare a private summary.” The model resolves the named app from the conversation. The catalog must identify that app. If it is disconnected, Anticipy offers access. After connection, the chosen hand reads within its granted scope. Preparing a summary does not become permission to email anyone.'),p('This example uses a fictional catalog app. The discovery model was tested on that distinction; it is not a claim that Quillbox is a real supported integration.','SmallA'),PageBreak()]
story += [p('Proof, and open edges.','TitleA')]
rows=[[p('<b>Check</b>'),p('<b>Evidence</b>')]]
for a,b in [('Browser','83 suites passed. Real Chrome smooth-scroll and removed-target fixtures. All three packaged downloads match source bytes.'),('Calendar','27 Swift checks; 9 actual Swift-body to Worker policy checks; real isolated EventKit save/readback/retry/undo; unsigned simulator build passed.'),('Text and API','3,001 brain/storage checks passed in CI, plus full Worker tests and TypeScript checks. The live owner delivery check produced one reply and one send attempt; SendBlue confirmed delivery.'),('Delivery UI','17 checks for exact reply/owner matching and honest queued, accepted, delivered and unknown states. Relevant UI and account-boundary checks passed.'),('Model judgment','Six live Claude Sonnet 4.6 discovery cases passed. Synthetic conversations/catalog covered unfamiliar names, pronouns, generic tasks, hypothetical use, hostile quotes and discontinued use.')]:rows.append([p(a),p(b)])
t=Table(rows,colWidths=[103,413],hAlign='LEFT');t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee5d6')),('LINEBELOW',(0,0),(-1,-1),0.4,colors.HexColor('#d8cbb8')),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [t]
story += [head('Still explicit'),p('Pendant audio is deferred: the decoder is missing, and no pending callback queue exists. Some other discovery collectors remain unused. Legacy semantic tape still exists elsewhere in the harness. These repairs do not certify every website, every API or the whole repository as free of hardcoded interpretation.'),p('An attempt recorded immediately before a crash can remain unconfirmed. Lost callbacks with a saved provider handle now have read-only reconciliation; attempts with no handle remain unconfirmed. The owner\'s current Chrome heartbeat still reports extension 0.15.0; the repaired download is 0.17.0. Calendar sync to a physical phone needs its own proof. Simulator success is not a CalDAV guarantee.'),head('Repository evidence')]
base='https://github.com/anticipation-labs/Anticipy/blob/cloudflare-backend/research/overnight-2026-09-07/'
for name,title in [('repair-status-2026-09-07.md','Repair status and technical paths'),('native-calendar-repair.md','Calendar and delivery UI evidence'),('browser-handoff-repair.md','Browser reproduction and package evidence'),('connection-dispatch-background.md','Connection latency and review findings')]:story.append(p(f'<link href="{base+name}" color="#936d36">{title}</link>','SmallA'))
OUT.parent.mkdir(parents=True,exist_ok=True)
SimpleDocTemplate(str(OUT),title='Anticipy repair brief - 7 September 2026',author='Anticipy Engineering',pagesize=(612,792),rightMargin=48,leftMargin=48,topMargin=65,bottomMargin=48).build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
