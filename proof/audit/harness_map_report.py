"""Render the dated harness map from reviewed source evidence; no product imports."""
from pathlib import Path
import json, html
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/overnight-2026-09-07/harness-map'
REV=json.loads((BASE/'inventory.json').read_text())['revision']
OUT=ROOT/'output/pdf/Anticipy-harness-explained-2026-09-07.pdf'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleA',fontName='Helvetica-Bold',fontSize=27,leading=31,textColor=colors.HexColor('#173633'),spaceAfter=13))
styles.add(ParagraphStyle(name='SubA',fontName='Helvetica-Bold',fontSize=13,leading=17,textColor=colors.HexColor('#008577'),spaceBefore=12,spaceAfter=7))
styles.add(ParagraphStyle(name='BodyA',fontName='Helvetica',fontSize=10.1,leading=14.3,textColor=colors.HexColor('#263d3b'),spaceAfter=8))
styles.add(ParagraphStyle(name='SmallA',fontName='Helvetica',fontSize=8,leading=10.7,textColor=colors.HexColor('#546562'),spaceAfter=6))
styles.add(ParagraphStyle(name='CellA',fontName='Helvetica',fontSize=8.5,leading=11.4,textColor=colors.HexColor('#253e3a')))
story=[];md=['# Anticipy: the harness explained\n',f'Audit source: `{REV}` on `cloudflare-backend`. 7 September 2026.\n']
def p(text,style='BodyA'):
 story.append(Paragraph(html.escape(text),styles[style]));md.append(text+'\n')
def title(n,text):
 if n>1:story.append(PageBreak())
 p(f'ANTICIPY / HARNESS MAP / {n:02d}','SmallA');p(text,'TitleA');md.append('## '+text+'\n')
def sub(text):p(text,'SubA')
def ref(path,line):
 full=ROOT/path;assert full.is_file(),path
 assert 0<line<=len(full.read_text().splitlines()),(path,line)
 return f'{path}:{line}'
def table(headers,rows,widths):
 vals=[[Paragraph('<b>'+html.escape(x)+'</b>',styles['CellA']) for x in headers]]
 vals += [[Paragraph(html.escape(str(v)),styles['CellA']) for v in row] for row in rows]
 t=Table(vals,colWidths=widths,hAlign='LEFT',repeatRows=1)
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#cce8e1')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f0f5f3'),colors.white]),('LINEBELOW',(0,0),(-1,0),0.5,colors.HexColor('#80b9ae'))]))
 story.append(t);md.append('| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+''.join('| '+' | '.join(str(v).replace('\n',' ') for v in row)+' |\n' for row in rows))
class Map(Flowable):
 def __init__(self):Flowable.__init__(self);self.width=504;self.height=246
 def draw(self):
  c=self.canv
  steps=[('1  HEAR OR READ','iPhone / Mac transcript, typed app message, or SendBlue text'),('2  REMEMBER + UNDERSTAND','Save the words; bring relevant context; ask models what is needed'),('3  MAKE ONE TRACKED TASK','Ask for missing details; record the scope and required approval'),('4  USE AN AVAILABLE HAND','Server draft/search | connected API | Chrome browser'),('5  CHECK + TELL YOU','Save the outcome; show it in the app; send text on supported paths')]
  for i,(a,b) in enumerate(steps):
   y=205-i*49;c.setFillColor(colors.HexColor('#e9f3ee'));c.roundRect(0,y,504,41,7,fill=1,stroke=0)
   c.setFillColor(colors.HexColor('#153f37'));c.setFont('Helvetica-Bold',10);c.drawString(12,y+25,a);c.setFont('Helvetica',9);c.drawString(12,y+10,b)
   if i<4:c.setStrokeColor(colors.HexColor('#008577'));c.line(252,y-1,252,y-7)
def footer(c,doc):
 c.setStrokeColor(colors.HexColor('#d8e4de'));c.line(45,38,550,38);c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#60736c'));c.drawString(45,25,'Anticipy | Source '+REV[:8]+' | 7 September 2026');c.drawRightString(550,25,str(doc.page))
title(1,'A helper with a notebook\nand a pair of hands')
p('The AI model supplies judgment. The harness is the surrounding software that gives it your words, memory and tools, keeps track of work, checks permission, and records what happened.')
story.append(Map());md.append('Flow: input -> saved event -> context and memory -> model judgment -> tracked task -> permitted hand -> checked result -> app/text.\n')
sub('In very small words')
p('You say something. Anticipy remembers it. She asks: "Is there something useful I should do?" If she needs a detail, she asks you. If she can prepare something, she tries. Before an external effect, the task must have the right authority. Then she should show what actually happened.')
sub('The honest verdict')
p('The main loop is connected and has real working examples. The product is not completely wired. Whole-conversation execution, pendant transcription and the native iPhone calendar writer have concrete gaps. App and text delivery are also not one uniformly reliable path.')
p('Trace: '+ref('brain/worker.py',5097)+'; '+ref('brain/anticipy_core.py',1575)+'; '+ref('brain/workflow.py',628),'SmallA')
title(2,'How a quote becomes work')
p('Illustration, not a new live test: you say, "We already booked the room. I still need a private note telling the team where to meet. Keep it here for me."')
table(['Stage','What the harness should do'],[
('Words','Keep the original transcript and speaker/source evidence. "Already booked" is history; it does not authorize another booking.'),
('Context','Bring the earlier conversation, owner identity/timezone, relevant memories, and current task state to the model.'),
('Judgment','Decide what is unfinished and useful. Check whether the intended recipient or place is ambiguous. Quotes and retrieved pages are evidence, not permission.'),
('Preparation','Produce the private note using the supplied facts. Do not replace it with instructions telling you how to write one.'),
('Effect + result','A private note is different from sending it. External effects need current scoped authority; the result is checked against the actual request.')],[91,413])
sub('Memory is three different things')
p('D1 is the shared record book: accounts, incoming events, task rows, connections and retry records. Per-owner SQLite is the brain notebook: raw episodes, entities and relationships, promises/open loops, distilled profile facts and procedures. R2 stores durable snapshots of that notebook; it is not the reasoning engine.')
p('Recall uses word-based candidate retrieval and a graph walk, not embeddings. Models extract and relate facts; provenance, retirement and expiry affect what can reach actions. Retrieval limits can still miss a relevant memory. Backups prove persistence, not correct recall.')
p('Trace: '+ref('brain/memory.py',770)+' / :942 / :1539; '+ref('brain/container_entry.py',257)+'; '+ref('brain/readiness.py',1)+'; '+ref('brain/server_work.py',1),'SmallA')
title(3,'Feature map: hearing and thinking')
rows1=[
('Phone speech','Connected','On-device transcription -> buffered event upload -> worker. Capture quality still needs device use.','app/ios/Anticipy/AnticipyApp.swift:2028'),
('Mac speech','Merged in source','Mic/system meeting capture -> TranscriptWire -> same Cloudflare API. Installation of the repaired Mac binary is separate.','app/macos/AnticipyMac/MacApp.swift:40'),
('Pendant','Disconnected','BLE/battery/gap handling exists. The app sets onOpusFrame to nil; no Opus-to-PCM decoder feeds transcription.','app/ios/Anticipy/AnticipyApp.swift:2090'),
('Typed + text input','Connected','app_reply and sms_reply converge in handle_inbound, after owner checks and shared connection-command dispatch.','brain/worker.py:4324'),
('Device context','Connected, bounded','Consent-based contact names and upcoming calendar titles/times become profile evidence. This is not full inbox/file access.','app/ios/Anticipy/LifeContext.swift:61'),
('Speech judgment','Connected','Contextual destination, ownership, readiness and effect judgments feed the task decision. Legacy meaning rules remain.','brain/anticipy_core.py:1575'),
('Memory','Connected','Ingestion, retrieval, open loops, profile consolidation, expiry, imported-fact provenance and veto paths exist.','brain/memory.py:708'),
('Proactive clock','Connected','Worker reviews open loops on a schedule; pending input, local quiet hours and outreach budgets constrain interruptions.','brain/worker.py:5155'),
('Conversation sorter','Observation only','Default off. Requesting on is explicitly downgraded to shadow; it cannot replace the live per-event funnel.','brain/worker.py:3660'),
('Training examples','Embedded in prompts','Examples are copied into Python prompts. Editing EXEMPLARS.md alone does not change runtime behavior.','brain/orchestrator.py:18')]
table(['Feature','Status and actual path'],[(a,b+'. '+c+'\n'+d) for a,b,c,d in rows1],[103,401])
title(4,'Feature map: doing and reporting')
rows2=[
('Task lifecycle','Connected','Versioned plans, scoped approval, claims/leases, cancellation, needs-user states and receipts. These reduce duplicate effects; they do not prove every provider action.','brain/workflow.py:991'),
('Server hand','Live example proven','Public research and private composition run on the server. A separate result review checks whether the requested artifact was actually produced.','brain/worker.py:5411'),
('Connected API hand','Connected, limited proof','Model selects a real catalog tool, validates arguments/account/effects; worker invokes /hands/api/run. Broad multi-app sequences are not established.','brain/hands.py:1005'),
('Chrome hand','Live fixture proof','Paired extension claims browser jobs, reads pages, asks the model, clicks/types, heartbeats and records outcomes. Login and uncertain effects can hand back.','extension/background.js:1639'),
('Browser memory','Connected','Procedure and recipe recall are imported by the browser loop. Stored recipes are checked for applicability before reuse.','extension/agent_loop.js:8'),
('Supervised reading','Connected','Separate browser lane gathers witnessed facts, with narration/veto-related memory ingestion. Distinct from unrestricted background account access.','extension/background.js:1159'),
('Native calendar hand','Missing executor','Policy, lane declarations and queue UI exist; no EventKit event-write executor was found in app source. Calendar reads do exist.','app/ios/Anticipy/Views/ContentView.swift:2909'),
('App connections','Live offer/command proof','Task access offers + consent links + OAuth provider adapter + durable command retries. Link creation is not completed OAuth consent.','migration/workers/src/connections/dispatch.ts:1'),
('App + text delivery','Connected, uneven','Task questions/notices are persisted; direct in-app replies suppress SMS. Direct SMS replies still have a send-before-app-history failure window.','brain/conversation.py:371'),
('Lifecycle + privacy','Connected','Owner containers, backups, deletion fences, auth, account reset and fleet status are wired. UI-free local environment has no model brain running.','migration/workers/brain/src/index.ts:215')]
table(['Feature','Status and actual path'],[(a,b+'. '+c+'\n'+d) for a,b,c,d in rows2],[103,401])
title(5,'What exists but is not finished')
gaps=[
('1. Calendar promise without a writer','The app says an iPhone calendar change will be picked up, but only policy/display references to that lane were found. LifeContext reads EventKit; it does not save events. Do not describe this native hand as working.'),
('2. Pendant audio stops at the phone','startPendantTranscription explicitly clears the audio callback. Firmware receipts also say not built/not flashed. BLE connection is not usable listening.'),
('3. Whole-conversation action path','sorter.mode defaults off; worker forces on -> shadow because the shared action funnel is not extracted. Individual events still own live judgment.'),
('4. Proactive app-discovery inputs','recordUserSaidIt, recordObservedHost, recordSignUpDomain, recordLinksSeen and recordAnswerToAsk have wrappers but no external production caller found. The connected-account sweep is wired.'),
('5. Periodic app nudges','cron.ts handles a five-minute nudge/reminder tick, but checked-in production wrangler.jsonc registers only the nightly tick. The live schedule was not independently re-read. Task-specific access offers are a separate working path.'),
('6. Alternative conversation grouping','brain/links.py has no static import path from the deployed Python entry points. The worker does persist continuation links; this alternate grouping helper is not the live brain implementation.'),
('7. Meaning rules still survive','shard_too_thin still uses word/novel-token counts to suppress actions. Anaphoric linking and degraded third-person filtering remain registered legacy tape. The no-hardcoded-meaning goal is not fully met.'),
('8. Text-first is not uniform','reply_in_app intentionally suppresses direct SMS replies. Conversation.say records a turn before sending; transport failure can precede the app-history write and a repeat can be deduped. This is a delivery architecture gap, not just nighttime.')]
table(['Gap','Evidence-based meaning'],gaps,[134,370])
p('Source anchors: AnticipyApp.swift:2090; worker.py:3660 and :4381; signals.ts:826-1245; wrangler.jsonc:250; content references in inventory.json. No product repair was made in this audit.','SmallA')
title(6,'What has actually been proved')
table(['Evidence','What it proves / what it does not'],[
('New checks in this audit','132 targeted Python checks passed in 1.20 s: sorter mode, segment tape, research wiring, memory-to-hand context, connection dispatch, task-access notices and pending questions. No paid model calls were started.'),
('Live readback, 18:53-18:54 UTC','API health HTTP 200. Correctly authenticated fleet read returned 8 served owners and no failed entries, brain release a4f4871a. Availability does not prove semantic quality or every task.'),
('Earlier real texting','A real SendBlue input received a clarification; the contextual reply then received a private draft. Provider delivery was observed. This was conversation fulfillment, not proof of a held job resuming.'),
('Earlier server artifact','An actual live worker queued a private-note request, composed it, checked fulfillment, stored matching text-digest evidence, and delivered it in-app. 82.84 s is too slow for a short draft.'),
('Earlier browser fixtures','Five controlled website cases used real Chrome and the production model proxy. A separate queued comparison passed claim/lease/click/receipt flow in 53.258 s. They do not establish every real website or the owner\'s installed extension.'),
('Earlier model contrasts','30/30 contextual speech contrasts and 12/12 local ingestion/planning outcomes passed. The latter are planning outcomes, not 12 executed real-world tasks.')],[136,368])
sub('Priority order from this evidence')
p('First reconcile the native-calendar promise with a real executor or truthful unavailable state. Then unify durable reply delivery across app/text. Complete the whole-conversation funnel and its generalistic tests before retiring the shard rule. Wire the missing app signals and their schedule only with ownership and interruption controls. Pendant decoding/build/device proof is its own project.')
p('Detailed proof files: harness-map/targeted-tests.txt; server-work-live-results.json; browser-production-results.json; browser-queue-results.json; ambient-context-model-results.json; ambient-context-worker-results.json. Earlier evidence keeps its original scope and date.','SmallA')
title(7,'The technical map and its limits')
sub('External APIs and execution surfaces')
table(['Service','Role in this branch'],[
('Cloudflare','API Worker + D1 records; per-owner Container/Durable Object brain; R2 memory snapshots and evidence assets.'),
('Gemini + OpenRouter','Model transports for the Python brain and the authenticated /agent/llm browser proxy. Model/transport selection depends on deployment configuration.'),
('Brave + Tavily','Public research search providers. A private draft can use supplied context without web search.'),
('Composio','Connection catalog, OAuth/account connections and connected tool execution. A connected service still needs the correct account, tool schema and effect authority.'),
('SendBlue','Inbound /sms/sendblue and outbound text delivery. Active Twilio fallback was removed; compatibility helpers/comments remain. /sms/inbound is retired.'),
('Apple + Chrome','Apple on-device speech and permissioned context; Chrome extension browser execution. TestFlight distribution uses CI/App Store Connect, not laptop signing.')],[125,379])
sub('Every tracked area was inventoried')
p('2,723 tracked files: app 293; brain 34 (31 Python modules); migration 201; extension 125; firmware 250; backend 97; spike 39; tests 200; proof 1,015; overnight 44; research 330; docs 30; design 18; output 7; other root/config/site files 40.')
p('All 61 API TypeScript modules are reachable through the static import graph (including type imports); that does not mean every exported function runs. Python static traversal reaches every brain module except the package marker and links.py. The full path census and route-dispatch source lines are included in tracked-files.tsv and inventory.json.')
p('backend/pb_public still feeds live Worker assets. backend hooks/migrations are historical PocketBase material. spike/two-hands includes contracts imported by production: it is not all disposable. HQ/fellows/admin routes are registered alongside the consumer API but are separate product surfaces. Proofs, experiments, firmware receipts and design documents are not automatically runtime features.')
sub('Scope you can trust')
p('This was a repository-wide inventory and source-path audit at '+REV[:8]+', not a line-by-line correctness review of 2,723 files. Binary contents, every third-party service and every possible user journey were not re-tested. Historical comments were checked against executable code where findings depended on them. All gaps are source findings unless specifically labeled live proof.')
p('Entry points: migration/workers/src/index.ts:166; brain/container_entry.py:328; brain/worker.py:5097; extension/manifest.json:26. Reproduce the map by following those entry points and the stored inventory.','SmallA')
OUT.parent.mkdir(exist_ok=True,parents=True)
SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),leftMargin=45,rightMargin=46.28,topMargin=38,bottomMargin=52,title='Anticipy: the harness explained',author='Anticipy repository audit').build(story,onFirstPage=footer,onLaterPages=footer)
(BASE/'REPORT.md').write_text('\n'.join(md).rstrip()+'\n')
(BASE/'features.json').write_text(json.dumps({'revision':REV,'features':[{'feature':a,'status':b,'behavior':c,'source':d} for a,b,c,d in rows1+rows2],'gaps':[{'gap':a,'finding':b} for a,b in gaps]},indent=2)+'\n')
print(OUT)
