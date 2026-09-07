"""Build the evidence-based morning audit; refresh from preserved replay results."""
from pathlib import Path
from datetime import datetime, timezone
import json, html
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, Flowable, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/Anticipy-harness-audit-2026-09-07.pdf'
pdfmetrics.registerFont(TTFont('Arial','/System/Library/Fonts/Supplemental/Arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','/System/Library/Fonts/Supplemental/Arial Bold.ttf'))
pdfmetrics.registerFont(TTFont('Georgia','/System/Library/Fonts/Supplemental/Georgia.ttf'))
INK=colors.HexColor('#222620'); MUTED=colors.HexColor('#60685F'); CREAM=colors.HexColor('#F5F3EA'); TEAL=colors.HexColor('#23675B'); GOLD=colors.HexColor('#926B37'); LINE=colors.HexColor('#DCDDD3')
styles={
 'title':ParagraphStyle('title',fontName='Georgia',fontSize=35,leading=40,textColor=INK,spaceAfter=20),
 'h1':ParagraphStyle('h1',fontName='Georgia',fontSize=25,leading=30,textColor=INK,spaceAfter=15),
 'h2':ParagraphStyle('h2',fontName='ArialBold',fontSize=13,leading=17,textColor=TEAL,spaceBefore=13,spaceAfter=7),
 'body':ParagraphStyle('body',fontName='Arial',fontSize=10.5,leading=15,textColor=INK,spaceAfter=9),
 'small':ParagraphStyle('small',fontName='Arial',fontSize=8.3,leading=11.5,textColor=MUTED,spaceAfter=5),
 'label':ParagraphStyle('label',fontName='ArialBold',fontSize=9,leading=12,textColor=TEAL,spaceAfter=10),
}
def clean(s):
 return str(s).replace('\u2011','-').replace('\u2013','-').replace('\u2014','-').replace('\u2192',' > ').replace('\u00a0',' ')
def P(s,style='body'):return Paragraph(clean(s),styles[style])
def E(s):return html.escape(clean(s))
def gap(n=8):return Spacer(1,n)
def section(k,title,body=None):
 story.extend([P(k.upper(),'label'),P(title,'h1')])
 if body:story.append(P(body))
def rows_table(rows,widths,header=True):
 data=[[P(E(x),'small') for x in row] for row in rows]
 t=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1 if header else 0)
 t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),0.5,LINE)]+([('BACKGROUND',(0,0),(-1,0),CREAM)] if header else [])))
 return t

def page(c,doc):
 c.setFillColor(CREAM);c.rect(0,0,612,792,fill=1,stroke=0)
 c.setStrokeColor(TEAL);c.setLineWidth(2);c.line(48,750,564,750)
 c.setFont('ArialBold',8);c.setFillColor(TEAL);c.drawString(48,760,'ANTICIPY  /  ENGINEERING AUDIT')
 c.setFont('Arial',7.5);c.setFillColor(MUTED);c.drawString(48,29,'7 SEPTEMBER 2026  |  cloudflare-backend  |  Evidence, not a guarantee of zero defects')
 c.drawRightString(564,29,str(doc.page))

class Journey(Flowable):
 def __init__(self): Flowable.__init__(self);self.width=516;self.height=370
 def draw(self):
  stages=[('1','Hear or read','On-device speech, typed words, or a SendBlue reply.'),('2','Keep the context','Who said it, the exact words, earlier turns, time and memory.'),('3','Decide what helps','Models judge meaning, ownership, missing details and effects.'),('4','Make a durable task','Save the task and its approval state before promising progress.'),('5','Use the right tool','Connected API, paired browser, phone calendar, or research.'),('6','Check what happened','Inspect the real result; keep evidence and uncertain outcomes.'),('7','Bring it back','Save the result in the app. Text through SendBlue when allowed.')]
  c=self.canv
  for i,(n,t,b) in enumerate(stages):
   y=326-i*51
   c.setFillColor(colors.white);c.roundRect(0,y,516,44,8,fill=1,stroke=0)
   c.setFillColor(TEAL);c.circle(20,y+22,11,fill=1,stroke=0)
   c.setFillColor(colors.white);c.setFont('ArialBold',10);c.drawCentredString(20,y+18.5,n)
   c.setFillColor(INK);c.setFont('ArialBold',10);c.drawString(42,y+27,t)
   c.setFillColor(MUTED);c.setFont('Arial',9);c.drawString(42,y+11,b)

people=json.loads((ROOT/'proof/audit/corpus/people.json').read_text())['people']
labels=('overnight-final-development-998','overnight-final-development-recovery-998','overnight-final-heldout-998')
observations={}
for label in labels:
 for f in (ROOT/'work/audit/transcripts'/label).glob('*/result.json'):
  d=json.loads(f.read_text())
  if d.get('state')=='observed_needs_semantic_review':observations[d['person_id']]=d
checked=datetime.now(timezone.utc).strftime('%H:%M UTC')
stall_file=ROOT/'work/audit/overnight-stall-backlog-1.json'
stall=json.loads(stall_file.read_text()) if stall_file.exists() else {}
story=[]
story.extend([gap(22),P('THE MORNING RECORD','label'),P('A clear view<br/>of the harness','title'),P('How Anticipy turns your words into useful work.<br/>What failed, what changed, and what has been proved.'),gap(18)])
story.append(rows_table([['ON YOUR PHONE','IN THE BACKEND'],['Build 165 is valid and available to the internal TestFlight group. Update in TestFlight; installation on your physical phone is not remotely confirmed.','SendBlue-only runtime is deployed. A missing webhook secret was found on the live API and repaired on both the API and provider.']], [258,258]))
story.extend([gap(16),P('The most important finding','h2'),P('A new live test exposed false completion: Anticipy marked a drafting task done with web instructions about making a draft, rather than the requested draft itself. This remains unresolved. Separately, the live SendBlue endpoint returned 503 because its webhook secret was missing; that configuration is now repaired.'),P('This report records actual observations. It does not certify every route, every connected account, every carrier delivery, or twenty days of use. The open work is listed plainly.'),gap(18),P(f'Prepared at {checked}. Completed planning observations: {len(observations)} of 50 authored people. Those are ingestion and planning traces, not 50 completed real-world errands.','small'),PageBreak()])
section('01 / The product','You live your day.<br/>Anticipy carries the thread.','The harness is the machinery around the AI: what it can hear, what context it receives, what tools it may use, what needs approval, and how it checks the result. A model alone does not provide those things.')
story.append(Journey())
story.extend([P('One example, three different meanings','h2'),P('<b>“The kids got added to the calendar for 3 PM.”</b> reports completed work. It should not create another event. <b>“Add pickup at 3 PM.”</b> requests work. <b>“Yes”</b> depends on the pending question. The full conversation must decide the meaning; a keyword or word count cannot.'),P('The original quote stays attached to the task. Memory may explain who “Sarah” is; it cannot silently invent an end time, treat a past event as a new instruction, or prove that a calendar was updated.'),PageBreak()])
section('02 / The phone','The interface failures were real.','The screenshots exposed overlapping controls, stale listening cards, long answers covering capture controls, duplicate task views, and a misleading delivery caption.')
story.append(rows_table([['FAILURE','REPAIR AND EVIDENCE'],['Reply box / Send button obscured','Keyboard-aware bottom layout. Inline reply focus hides the competing composer and listening control. Tested in the simulator.'],['UI stops responding','Reproduced a LazyVStack/scroll interaction with high CPU and an empty accessibility tree. Changed the layout and scroll behavior; repeated interaction stayed responsive.'],['Old answers reappear while listening','Build 164 snapshots existing reply identities, including the first history fetch. Pause/resume keeps new answers; a fresh capture does not replay old completed ones.'],['Huge answers hide controls','Capture cards show a bounded preview with a full-details view. The long synthetic result remained usable while recording and after pause/resume.'],['Links visible but not usable','Build 165 makes HTTP/HTTPS URLs tappable in answers, questions and expanded details. An actual simulator tap opened the exact test URL in Safari.'],['Duplicate or uncertain actions','Task identity and source-event identity drive presentation and reply deduplication. An uncertain send is not silently repeated.'],['Nighttime behavior invisible','A moon/quiet-hours caption uses the server account policy. The backend now persists missing-access notices before deciding whether to text.']], [157,359]))
story.extend([P('A reply could be generated and then lost','h2'),P('The final review found that one stage could discard the actual clarification or memory answer and keep an earlier “on it” acknowledgement. The repair preserves the real response and checks ambiguous contacts. Targeted model replays now return the missing-name question and the requested memory answer. A live owner-scoped observation also recovered the actual missing-name question. The same run exposed a separate false-completion defect downstream.'),P('Limits of the phone test','h2'),P('Build 164 was compiled for the simulator and exercised by computer use. Microphone-state and responsiveness checks were observed; these do not prove recognition accuracy for every accent, noisy room, Bluetooth route, or physical iPhone.'),PageBreak()])
section('03 / Listening view','A long answer can stay small.','This is an actual simulator capture from the repaired app. The card preview is bounded; the full answer is available separately, and recording controls remain reachable.')
img=ROOT/'work/audit/overnight-capture-164-resumed.png'
if img.exists():
 from PIL import Image as PILImage
 w,h=PILImage.open(img).size
 story.append(Image(str(img),width=225,height=225*h/w,hAlign='CENTER'))
story.extend([gap(8),P('Evidence: overnight-capture-164-resumed.png; source and checks in research/overnight-2026-09-07/ui-164.md. The content is a synthetic test fixture.','small'),PageBreak()])
section('04 / Text first','A text is an input, not a notification badge.','The intended loop is: SendBlue receives your message, the API authenticates and stores it under your account, the brain reads the conversation, and an answer updates the same task. The app and Messages are two entrances to that conversation.')
story.append(rows_table([['STEP','WHAT IT DOES'],['Receive','POST /sms/sendblue checks the shared sb-signing-secret, resolves the owner, and stores the event. The retired /sms/inbound endpoint returns 410.'],['Understand','The reply model sees the current task, its pending question, its version, and the surrounding owner conversation. “Yes” has no hardcoded meaning.'],['Continue','A clarification can fill missing information. Approval can resume the relevant task. A new request or a memory note must not be mistaken for approval.'],['Return','The app result is persisted first. SendBlue can then deliver an allowed text. Provider acceptance and delivery to the phone are different facts.'],['Nighttime','Unsolicited proactive texts defer during quiet hours. An invited missing-detail question may text at night. A saved in-app blocker remains visible.']], [97,419]))
story.extend([P('Verified on the live system','h2'),P('The original endpoint returned 503. After repair, unsigned requests return 403 and a correctly signed malformed body reaches parsing and returns 400. The provider’s saved secret and URL were read back after refresh. No real-person test text was sent during this verification.'),P('Still limited','h2'),P('A carrier-origin reply-to-action test is still separate from authentication proof. The SendBlue account reports Free API Mode with 1 of 10 contacts. Delivery callbacks are not yet represented as per-task delivery receipts in the phone UI.'),PageBreak()])
section('05 / The tools','Four ways to do work.','The model selects a route from actual capability and account state. Code enforces the chosen effect and permissions. A missing connection must become a clear next step, rather than a claim that work is underway.')
story.append(rows_table([['TOOL','USED FOR','BOUNDARY'],['Connected API','Read or act in an account connected through Composio. Tool names and schemas come from its runtime catalog.','Account ownership, usable connection, declared effects, tool schema, write permissions and approval.'],['Browser','Use the owner’s paired Chrome for a private website, form, or task that needs that session.','Pair credential, owner scope, heartbeat, task lease, action journal, evidence and final verification.'],['Phone calendar','Perform the declared calendar operation on the phone through EventKit.','iOS permission, canonical calendar task shape, task approval and result receipt.'],['Research / memory','Read public sources or recall what the owner previously supplied.','A read-only answer cannot stand in for access to a private document or a live calendar.']], [102,220,194]))
story.extend([P('What the browser actually proved','h2'),P('Five isolated website scenarios passed through the live Gemini 3.1 Pro proxy: price comparison, a synthetic appointment, a login wall, a capacity conflict and page-instruction injection. A further comparison used the real backend queue, claim, lease, evidence upload and completion path: four model calls, 53.3 seconds, both prices correct.'),P('Chrome pages were synthetic and external website access was blocked. Published extension 0.16 passed its checks, but the personal installed 0.15 extension remains unchanged because automated access to its management page was blocked.','small'),PageBreak()])
section('06 / Memory and judgement','Remember the evidence.<br/>Check the present.','Memory should help Anticipy keep up with your life. It should not act as a bag of facts that overrides what you just said, or as a substitute for reading a source you explicitly asked it to check.')
story.append(rows_table([['CONTEXT','HOW IT SHOULD BE USED'],['Conversation','Keep the exact words, speaker evidence, previous turns and time together. A correction can supersede a previous statement.'],['Imported contacts and notes','Preserve provenance. Similar names are not interchangeable; imported text is context, not an instruction to act.'],['Durable memory','Each owner has separate memory. Container memory snapshots must persist in R2; a process being alive does not prove its memories are durable.'],['Current account data','Read the actual calendar, document, mail or service when the task requires its present contents. Ask for access when it is unavailable.']], [140,376]))
story.extend([P('Measured repairs','h2'),P('Grounding checks were moved to contextual model judgements for the repaired path. The speech classifier preserves completed tense; the memory fill step uses provenance and the actual missing fields. A separate effect judgement distinguishes a private draft from sending or saving it externally.'),P('20 effect contrasts passed with the real model. Recorded whole-worker replays distinguish private drafting from a compound request that writes notes and a calendar. Twelve grounding cases, sixteen information-request cases, fourteen contextual replies and sixteen memory-relation cases have separate evidence.'),P('Open work','h2'),P('Several legacy meaning shortcuts remain elsewhere in the code, and the retirement checks still identify three registered pieces. Contextual offers for a named missing app now work on a live queued task. Useful read-only preparation before a compound external action still needs work. One of twelve ambient cases also wrongly suppressed a requested private draft as machine dictation; that failure is preserved and unresolved.'),PageBreak()])
section('07 / Verification','What a passing test does - and does not - prove.')
story.append(rows_table([['EVIDENCE','OBSERVATION','SCOPE'],['Backend tests','3,109 passed; 2 skipped','Final reply-handoff candidate, including storage failures, ownership and restart behavior.'],['Worker API suite','Passed, with TypeScript checks','Contract behavior, actual local D1/workerd fixtures and modern SendBlue wire format.'],['Live API release','34 account/ownership checks passed','Signup, isolation, profile, deletion and active source. Extra webhook probe found the missed configuration defect.'],['Live brain deployment','Eight workers verified on latest source','At15:58UTC, CI34140365066 verified all8 current processes, source hashes and durable memory snapshots.'],['Browser scenarios','5 direct scenarios + 1 full queue comparison','Real Chrome DOM and live model; fixture websites, no real purchase or booking.'],['Ambient conversations','11 of 12 planning outcomes met','Seven quiet cases stayed quiet. One licensed private draft was incorrectly ignored as dictation.'],['Persona replay',f'{len(observations)} / 50 observed at report generation','Real models, local HTTP/D1, stored memory, questions and planned work. Manual planning review; no provider execution arms.'],['Live missing-access notice','PASS' if stall.get('passed') else 'Pending successful live observation','Seven queued tasks each received a notice in67.7seconds. Separate live Gmail offer in9.37seconds. Tasks cancelled; fictional phone restored.']], [123,155,238]))
story.extend([P('The test harness protects the user','h2'),P('Synthetic people have isolated accounts, contacts, history and tasks. Browser fixtures block non-test website traffic. Paid model calls use preserved spending ledgers within the authorized US$50 ceiling. Replays preserve failed runs and source hashes; a new run never overwrites an earlier failure.'),P('Observed planning is not completed work. Provider-origin SMS, real OAuth accounts, physical-device audio and a twenty-day life trial require their own evidence.','small'),PageBreak()])
section('08 / Release and remaining work','What is ready to use.')
story.append(rows_table([['AREA','CURRENT STATE'],['Your iPhone','Open TestFlight and update Anticipy to build 165. Apple reports the build VALID and Internal IN_BETA_TESTING. The earlier fresh signup confirmation came from you; no additional account reset was performed overnight.'],['Sanket','Build 165 is attached to the private test group. Apple refused another beta submission while build 159 is still in review. The tester remains NOT_INVITED and external installability is not confirmed.'],['Texting','SendBlue-only API and brain are live. Shared webhook authentication has been repaired and verified. Real carrier round-trip remains to be exercised.'],['Browser','Live synthetic pairing and full queue proof passed. The personal installed extension requires an allowed manual update; it was not secretly replaced.'],['Proactive setup','Contextual connection commands work through the stored-event API, including an affirmative follow-up. A blocked Gmail task now offers to connect Gmail. Arbitrary multi-step integration execution remains incomplete.'],['Task completion','A live draft request produced a web how-to answer and was marked done. This is a false completion. Results must be checked against the requested outcome before completion.'],['Compound tasks','Private drafting is no longer automatically classed as an external write. Useful preparation before a later external step and general multi-step API execution remain open.'],['Delivery presentation','Quiet-hour state is visible. Per-task provider delivery receipts and more natural browser-result presentation remain open.']], [127,389]))
story.extend([P('The next acceptance test','h2'),P('From the fresh phone flow: make a small spoken request, answer its missing-detail question in Messages, verify that the same task continues once, and inspect the actual result. Repeat with the browser closed, an unconnected source, a cancelled task and a failed network. Each failure should be visible and recoverable.'),PageBreak()])
section('09 / Evidence map','Follow any claim back to its source.')
for name,desc in [('STATE.md','Current handoff, release state and unresolved work.'),('ui-165.md','Tappable links, build165 and independent Apple availability check.'),('sendblue-retirement.md','Fallback removal, the live 503 discovery and authentication repair.'),('stall-notices.md','App-first browser/phone notices, quiet-hour deferral and exact-task deduplication.'),('browser-queue-results.json','Actual queue/claim/lease/evidence/completion result.'),('connection-live-results.json','Stored owner-event connection commands, real catalog/model and idempotent replies.'),('reply-handoff.md','Discarded answers, ambiguous contacts and the measured repair.'),('persona-planning-review.md','Per-person findings; queued planning is not completed execution.'),('morning-status.md','Current release, live false completion and the focused remaining work.')]:
 url='https://github.com/anticipation-labs/Anticipy/blob/cloudflare-backend/research/overnight-2026-09-07/'+name
 story.extend([P(f'<a href="{url}" color="#23675B">{name}</a>','h2'),P(desc)])
story.extend([P('Primary provider references','h2'),P('<a href="https://docs.sendblue.com/getting-started/webhooks/">SendBlue webhook authentication</a> - the signed delivery contract used for the configuration repair. The app’s audio source uses Apple on-device SpeechAnalyzer / SFSpeechRecognizer; the browser proof records the actual served model rather than assuming the repository default.','small'),P('The repository inventory under research/audit-2026-09-06/inventory preserves files, documentation, route candidates, tables and link candidates. An inventory is not proof that every item executes successfully.','small'),PageBreak()])
for start in range(0,50,5):
 section(f'Examples / {start+1}-{start+5}','Fifty people, fifty different lives.','Fictional evaluation examples. Each has separate contacts and prior context. The outcome below is the required behavior, not a claim that it has been executed.')
 for i,person in enumerate(people[start:start+5],start+1):
  observation=observations.get(person['id'])
  state='Ingestion/planning trace recorded' if observation else 'No final-revision trace recorded yet'
  story.extend([P(f'{i:02d}. {E(person["name"])} - {E(person["occupation"])}','h2'),P(E(person['transcript']['text'])),P('<b>Must happen:</b> '+E(person['evaluator_only']['required_outcome']),'small'),P('<b>Stress:</b> '+E(person['evaluator_only']['challenge'])+'. <b>Evidence:</b> '+state+'.','small')])
 if start<45:story.append(PageBreak())
OUT.parent.mkdir(parents=True,exist_ok=True)
SimpleDocTemplate(str(OUT),pagesize=(612,792),rightMargin=48,leftMargin=48,topMargin=63,bottomMargin=53,title='Anticipy - A clear view of the harness',author='Anticipy engineering audit').build(story,onFirstPage=page,onLaterPages=page)
print(OUT)
