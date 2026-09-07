"""Build the short cloud/local repository audit from measured evidence."""
from pathlib import Path
import json
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/Anticipy-codebase-map-2026-09-07.pdf'
DOC=ROOT/'research/overnight-2026-09-07/repository-state.md'
EVID=ROOT/'research/overnight-2026-09-07/repository-state-evidence.json'
ink=colors.HexColor('#18312f'); muted=colors.HexColor('#546460'); teal=colors.HexColor('#087f72'); pale=colors.HexColor('#e9f3ef'); amber=colors.HexColor('#9b642e')
styles={
 'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=25,leading=29,textColor=ink,spaceAfter=15),
 'deck':ParagraphStyle('deck',fontName='Helvetica',fontSize=12,leading=17,textColor=ink,spaceAfter=14),
 'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10,leading=14,textColor=ink,spaceAfter=8),
 'small':ParagraphStyle('small',fontName='Helvetica',fontSize=8.5,leading=11,textColor=muted,spaceAfter=7,wordWrap='CJK'),
 'label':ParagraphStyle('label',fontName='Helvetica-Bold',fontSize=10,leading=13,textColor=teal,spaceAfter=10),
 'cell':ParagraphStyle('cell',fontName='Helvetica',fontSize=9,leading=12,textColor=ink,wordWrap='CJK'),
 'head':ParagraphStyle('head',fontName='Helvetica-Bold',fontSize=9,leading=12,textColor=colors.white),
}
story=[];md=[]
def p(t,kind='body'):
 story.append(Paragraph(escape(t),styles[kind]));md.append(t+'\n')
def title(n,t,deck):
 if story:story.append(PageBreak())
 p('ANTICIPY / REPOSITORY AUDIT / '+str(n).zfill(2),'label');p(t,'title');p(deck,'deck');md.append('\n')
def table(headers,rows,widths):
 data=[[Paragraph(escape(x),styles['head']) for x in headers]]+[[Paragraph(escape(str(x)),styles['cell']) for x in r] for r in rows]
 t=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1)
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),ink),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('ROWBACKGROUNDS',(0,1),(-1,-1),[pale,colors.HexColor('#f8faf8')]),('LINEBELOW',(0,0),(-1,-1),.35,colors.white)]))
 story.extend([t,Spacer(1,12)]);md.append('| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(str(x) for x in r)+' |' for r in rows)+'\n')

title(1,'The code is split.\nThe local copy is current.','The main checkout exactly matches GitHub. The larger problem is unfinished integration between branches, inconsistent runtime configuration, and tests that do not always exercise the deployed path.')
p('Measured September 7, 2026, 11:14-11:24 AM Vancouver. Product source snapshot: a4f4871a. Read-only comparisons; no feature branch was merged or reset.','small')
table(['Place','What is actually there'],[
 ('This Mac + cloudflare-backend','Same commit: a4f4871a. Zero commits ahead or behind. No tracked local modifications. Two untracked audit outputs are preserved.'),
 ('GitHub default: main','Different history; no iOS app, brain, or migration directory. An ordinary default-branch clone leads developers to the wrong product.'),
 ('issue-37-mac-ears / PR #59','11 branch-only commits; 49 current-app commits absent. A merge preview into current app source has no textual conflicts. Still needs integration tests.'),
 ('retire-pocketbase / PR #61','Stacked on the Mac branch, not current app source. 21 branch-only commits; 49 current-app commits absent. Direct integration has 12 conflicting files.'),
 ('jose_anticipy_system','Older migration branch: 2 branch-only commits, 357 current-app commits absent. It is not an interchangeable development baseline.')
],[151,353])
p('Why GitHub can look fine while developers collide','label')
p('PR #61 is clean against its selected older base. That does not mean it is clean against the app branch. It changes 404 files and removes about 26,800 lines, including renames of modules that current repairs still edit. GitHub also reports cloudflare-backend as unprotected; discipline alone currently coordinates direct writers.')
p('These counts describe divergence, not missing files or proof that someone lost work. No evidence of local tracked-code corruption was found.','small')

title(2,'One product. Three kinds of state.','The phone captures input. Cloudflare stores the record and runs the brain. The brain uses memory to decide what to prepare, ask, or do through connected tools.')
d=Drawing(504,144)
def box(x,y,w,h,label,sub):
 d.add(Rect(x,y,w,h,rx=7,ry=7,fillColor=pale,strokeColor=teal,strokeWidth=.8));d.add(String(x+9,y+h-17,label,fontName='Helvetica-Bold',fontSize=10,fillColor=ink));d.add(String(x+9,y+12,sub,fontName='Helvetica',fontSize=8,fillColor=muted))
def arrow(x,y,x2,y2):
 d.add(Line(x,y,x2,y2,strokeColor=teal,strokeWidth=1.2));tip = -5 if x2 > x else 5; d.add(Polygon([x2,y2,x2+tip,y2+3,x2+tip,y2-3],fillColor=teal,strokeColor=teal))
box(0,87,142,48,'iPhone / Mac','Speech, typed input, screens');box(181,87,142,48,'Cloudflare API','Accounts, routes, connections');box(362,87,142,48,'D1 database','Events, jobs, app records');arrow(143,111,177,111);arrow(324,111,358,111)
box(0,8,142,48,'Connected tools','Browser, APIs, device hands');box(181,8,142,48,'Python brain','Context, decisions, execution');box(362,8,142,48,'Memory + R2','Owner SQLite and snapshots');arrow(323,33,359,33);arrow(180,33,147,33);d.add(Line(433,87,433,73,strokeColor=teal));d.add(Line(433,73,252,73,strokeColor=teal));d.add(Line(252,73,252,56,strokeColor=teal));story.extend([d,Spacer(1,8)])
table(['State','Owner and location','Collision boundary'],[
 ('App records','Cloudflare D1: users, events, jobs, profiles, pairing and workflow state. API code: migration/workers/src/.','This is the migrated record store. A /api/collections URL does not mean PocketBase is still serving it.'),
 ('Brain memory','Per-owner memory.db + clock_state.json in the container; snapshots in R2 under owners/<owner_ref>/.','One production Durable Object/container per owner is intended to be the single writer. A second laptop worker using that same live identity is unsafe.'),
 ('Local test state','Wrangler local D1/R2/DO files plus a separate memory.db for each synthetic run.','Every developer/run needs its own state directory, ports and test identities. Sharing a SQLite file or fixture owner can collide.')
],[92,229,183])
p('Where the code lives','label')
p('iOS: app/ios/  |  Mac recorder: app/macos/  |  Brain: brain/  |  Browser: extension/  |  API: migration/workers/src/  |  Container control: migration/workers/brain/  |  Schema: migration/d1/','small')
p('PocketBase names are still in current source: brain/pb.py is an HTTP wrapper; backend/pb_hooks is legacy code; backend/pb_public still supplies live static assets. PR #61 moves/renames these. Deleting backend/ before integrating its asset move would remove source the current deployment still uses.')

title(3,'Where it is failing','These are observed defects and concrete risks. Healthy infrastructure does not prove that the assistant understands a conversation or completes a task correctly.')
table(['Finding','Impact / evidence','Status'],[
 ('Migration work is not integrated','Mac source targets retired Railway (health: 404). Public /download serves the old 1.0.0 DMG (2.52 GB). The capture repair exists in PR #59; PocketBase removal is in separate PR #61.','Open integration work'),
 ('Local server is not the current checkout','At audit start, port 8787 runs frozen worktree 998fca6. Its state is migration/workers/.wrangler/state. The local guide instead describes current source and work/mac-dev/state.','Wrong source'),
 ('Documentation gives conflicting instructions','The migration checklist still says the brain is undeployed and PocketBase is online on Railway. Live Cloudflare status now shows 8 running owners with current snapshots.','Docs stale'),
 ('Configuration diverges outside Git','SendBlue inbound secret differed from the Worker. Brain outgoing replies returned HTTP 403. Secrets were aligned and the verified sender configured on API and brain; a real text question and draft then completed.','Targeted path verified'),
 ('Meaning was decided by wording rules','Fluent volunteer planning was suppressed as machine dictation. Contextual classification replaced those overrides; 30/30 model contrasts and 12/12 local planning outcomes pass.','Deployed; ambient live task still unproven'),
 ('Task quality and delay remain','Previous live private artifact took 82.84 seconds. A queue entry or model acknowledgement is not a completed task. Browser pairing on the personal installation remains unproven.','Open product work'),
 ('Memory correctness is not availability','Current snapshots show persistence is running. They do not prove correct recall, no conflicting facts, or 20 days of reliable behavior. No current cross-owner corruption was demonstrated in this audit.','Further behavior proof needed')
],[112,295,97])
p('The new brain release a4f4871a is live: 8/8 owners, running source matches, snapshots current, deployment workflow 34150343842 passed. iOS remains build 165 from commit 844c8a38. A backend deployment does not create a new phone build.','small')

title(4,'Clean it without losing anyone\'s work','Reconcile the team around one integration history and one development recipe. Preserve working branches and databases while doing it.')
steps=[
 ('1. Freeze the comparison, not everyone\'s work.','Record current remote SHAs and each developer\'s branch. Use cloudflare-backend as the product base. Give each change its own checkout/worktree and commit exact file paths. Do not reset, force-push, or combine unrelated main history.'),
 ('2. Fix the local runtime mismatch.','Stop only the audit-owned frozen server after confirming no tests are using it. Start the prepared current-source launcher with its own work/mac-dev/state. Keep the old state as evidence; do not delete or point another worker at production memory.'),
 ('3. Integrate Mac capture first.','PR #59 has a conflict-free textual preview, but must be checked on a fresh integration worktree against the current iOS build, auth flow and live capture route. Preserve build 165 and increment correctly if iOS source changes.'),
 ('4. Restack the PocketBase removal.','Rebase or reconstruct PR #61 on the tested integration result in a new branch. Resolve the 12 conflicts against current behavior, including the brain, messaging, API entry point and both version files. Preserve renames and recent repairs; do not choose an entire side blindly.'),
 ('5. Prove the shipped path and then tidy.','Run the maintained tests against the Worker, verify the deployed commit and memory snapshots, then exercise capture -> question -> reply -> actual result. Remove obsolete launch instructions only with working replacements. Branch protection/default-branch changes need a coordinated repository decision.')]
for h,b in steps:p(h,'label');p(b)
p('What I did during this check','label')
p('Fetched the actual cloud branches, compared ancestry and commits, ran non-mutating merge previews, inspected the running local process and its working directory, read the storage/deployment code, and checked current live fleet health. No branches were merged, no developers\' files were reset, and no memory was deleted. The existing runtime mismatch is documented, not silently erased.')
p('Reproducible evidence','label')
p('research/overnight-2026-09-07/repository-state-evidence.json contains the branch comparison, exact conflicts, route observations and sanitized live status. Related PRs: github.com/anticipation-labs/Anticipy/pull/59 and /pull/61. This report is a current-state map, not a claim that all product failures are repaired.','small')

DOC.write_text('# Anticipy cloud/local codebase audit - September 7, 2026\n\n'+'\n'.join(md))
branch=json.loads((ROOT/'work/audit/cloud-branch-comparison.json').read_text())
live=json.loads((ROOT/'work/audit/cloud-audit-live-status-private.json').read_text())
evidence={'checked_at':'2026-09-07T18:20:00Z','head':'a4f4871aeab8a0b5e576a3b3a56d82c62d13a63a','branches':branch,'default_branch':'main','protected':False,'local_untracked':['output/playwright/','proof/audit/live_stall_notice.py'],'local_runtime':{'port':8787,'cwd':'/private/tmp/anticipy-overnight-998fca6/migration/workers','persist_to':'/Users/omarebrahim/Anticipy/migration/workers/.wrangler/state'},'retirement_conflicts':(ROOT/'work/audit/retire-pocketbase-merge-preview.txt').read_text().splitlines()[1:],'retirement_diff':{'files':404,'insertions':1230,'deletions':26814},'live':{'http':200,'served':live['served'],'failed_count':len(live['failed']),'version':live['version'],'workers':[{'running':w['child_running'],'source_sha256':w['source_sha256'],'snapshot_current':w['snapshot_current']} for w in live['workers']]}}
route=ROOT/'work/audit/cloud-route-observations.json'
if route.exists():evidence['routes']=json.loads(route.read_text())
EVID.write_text(json.dumps(evidence,indent=2)+'\n')
def footer(c,doc):
 c.saveState();c.setStrokeColor(pale);c.line(45,42,549,42);c.setFillColor(muted);c.setFont('Helvetica',8);c.drawString(45,28,'Anticipy | Codebase map | September 7, 2026');c.drawRightString(549,28,str(doc.page));c.restoreState()
SimpleDocTemplate(str(OUT),pagesize=(594,792),rightMargin=45,leftMargin=45,topMargin=35,bottomMargin=54,title='Anticipy codebase map - cloud, local and migration state',author='Anticipy engineering audit').build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
