"""Build the engineer brief and export the proposed, unexecuted case catalogue."""
from pathlib import Path
import csv, json, re, html, hashlib
import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
OUT=ROOT/'output/pdf/Anticipy-engineer-field-brief-500-scenarios.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
(ROOT/'tmp/pdfs/engineer-handoff').mkdir(parents=True,exist_ok=True)
FONTS=Path(reportlab.__file__).parent/'fonts'
pdfmetrics.registerFont(TTFont('Body',str(FONTS/'Vera.ttf')))
pdfmetrics.registerFont(TTFont('BodyBold',str(FONTS/'VeraBd.ttf')))
pdfmetrics.registerFont(TTFont('BodyItalic',str(FONTS/'VeraIt.ttf')))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='BodyItalic',boldItalic='BodyBold')
W,H=A4; M=43; CW=W-2*M
INK=HexColor('#173b35'); MUTED=HexColor('#52675f'); GOLD=HexColor('#cda65e'); PAPER=HexColor('#f6f3eb'); PALE=HexColor('#e9eee7'); LINE=HexColor('#d8ddd5')
NORMAL=ParagraphStyle('normal',fontName='Body',fontSize=10.7,leading=15.9,textColor=INK,spaceAfter=11)
SMALL=ParagraphStyle('small',parent=NORMAL,fontSize=9.0,leading=12.6)
CARD=ParagraphStyle('card',parent=NORMAL,fontSize=10.0,leading=13.3)
CARD_EXPECT=ParagraphStyle('expect',parent=CARD,fontSize=9.7,leading=12.8,textColor=MUTED)
H2=ParagraphStyle('h2',parent=NORMAL,fontName='BodyBold',fontSize=13.4,leading=17.4)
sections={}
raw=(HERE/'brief.md').read_text()
for s in raw.split('\n## ')[1:]:
 title,body=s.split('\n',1);sections[title]=body.strip()

def clean(s):
 for a,b in [('“','"'),('”','"'),('’',"'"),('‘',"'"),('→',' -> '),('—',' - '),('–','-'),('\u2011','-')]:s=s.replace(a,b)
 return s

def markup(s):
 s=html.escape(clean(s));s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
 return s

catalogue=[];groups=[]
for block in (HERE/'scenarios.txt').read_text().split('# ')[1:]:
 lines=block.strip().splitlines();num,title,surface,setup=[x.strip() for x in lines[0].split(' | ')]
 assert len(lines[1:])==20,(title,len(lines[1:]))
 cases=[]
 for i,line in enumerate(lines[1:]):
  attempt,expect=[x.strip() for x in line.split(' | ')]
  case={'id':f'{len(catalogue)+1:03}','category':title,'surface':surface,'setup':setup,
    'set':'Smoke' if i<2 else ('Reserved' if i>=16 else 'Broad'),
    'try':attempt,'expected':expect,'status':'NOT RUN','observed':'','evidence_url':'',
    'failure_cause':'','fix_commit':'','retest_status':'','latency_seconds':'','model_cost_usd':'',
    'installed_build':'','extension_version':'','tester':'','run_utc':''}
  catalogue.append(case);cases.append(case)
 groups.append({'number':num,'title':title,'surface':surface,'setup':setup,'cases':cases})
assert len(catalogue)==500 and len({x['try'] for x in catalogue})==500
assert sum(x['set']=='Smoke' for x in catalogue)==50
assert sum(x['set']=='Reserved' for x in catalogue)==100
(HERE/'scenarios.json').write_text(json.dumps({'status':'Proposed and unexecuted','case_count':500,'cases':catalogue},ensure_ascii=False,indent=2)+'\n')
with (HERE/'Anticipy-500-scenario-result-sheet.csv').open('w',newline='',encoding='utf-8-sig') as f:
 wr=csv.DictWriter(f,fieldnames=list(catalogue[0]),lineterminator='\n');wr.writeheader();wr.writerows(catalogue)

c=canvas.Canvas(str(OUT),pagesize=A4,pageCompression=1)
c.setTitle('Anticipy | Engineer field brief and 500 acceptance scenarios')
c.setAuthor('Anticipy engineering handoff')
c.setSubject('Phone-first validation, agentic harness, text-first connections, browser execution and memory')
page_specs=[];layout_checks=[]

def para(text,x,y,width=CW,style=NORMAL):
 p=Paragraph(text,style);w,h=p.wrap(width,2000)
 if y-h<39:raise ValueError(f'Page {c.getPageNumber()} overflow {y-h:.1f}: {text[:65]}')
 p.drawOn(c,x,y-h);layout_checks.append({'page':c.getPageNumber(),'bottom':round(y-h,2),'height':round(h,2)})
 return y-h

def chrome(section,appendix=False):
 c.setFillColor(PAPER);c.rect(0,0,W,H,fill=1,stroke=0)
 c.setFillColor(INK);c.setFont('BodyBold',9);c.drawString(M,H-29,'ANTICIPY')
 c.setFont('Body',8);c.setFillColor(MUTED);c.drawRightString(W-M,H-29,'ENGINEER FIELD BRIEF  /  07 SEP 2026')
 c.setStrokeColor(LINE);c.line(M,H-42,W-M,H-42)
 c.setFont('Body',7.7);c.drawString(M,23,'PROPOSED TESTS - NOT EXECUTED' if appendix else 'PHONE FIRST. CONTEXT INTACT. RESULTS VERIFIED.')
 c.drawRightString(W-M,23,f'{c.getPageNumber():02}')
 c.bookmarkPage(f'page{c.getPageNumber()}')
 page_specs.append({'page':c.getPageNumber(),'title':section,'type':'cases' if appendix else 'brief'})

def title(kicker,text,sub=''):
 c.setFillColor(GOLD);c.setFont('BodyBold',8.8);c.drawString(M,H-69,kicker.upper())
 y=para(markup(text),M,H-81,style=ParagraphStyle('title',fontName='BodyBold',fontSize=25,leading=29.5,textColor=INK))
 if sub:y=para(markup(sub),M,y-13,style=SMALL)
 return y-22

def body(text,y,style=NORMAL):
 for p in text.split('\n\n'):
  if not p.strip():continue
  # Keep authored numbered steps on separate readable lines.
  lines=p.splitlines()
  if len(lines)>1 and all(re.match(r'^\d+\.',l) for l in lines):
   for l in lines:y=para(markup(l),M,y,style=style)-8
  else:y=para(markup(p.replace('\n',' ')),M,y,style=style)-11
 return y

def page(kicker,name,key,extra=None):
 chrome(name);y=title(kicker,name);y=body(sections[key],y)
 if extra:y=body(extra,y)
 c.showPage()

# 1. Cover
c.setFillColor(INK);c.rect(0,0,W,H,fill=1,stroke=0);c.bookmarkPage('page1');page_specs.append({'page':1,'title':'Make it earn trust','type':'cover'})
c.setFillColor(GOLD);c.circle(M+8,H-66,7,fill=1,stroke=0);c.setFont('BodyBold',17);c.setFillColor(PAPER);c.drawString(M+27,H-72,'Anticipy')
c.setFillColor(GOLD);c.setFont('BodyBold',10);c.drawString(M,H-126,'THE ENGINEER FIELD BRIEF')
cover=ParagraphStyle('cover',fontName='BodyBold',fontSize=43,leading=48,textColor=PAPER)
y=para('Make it<br/>earn trust.',M,H-159,CW,cover)
y=para('Install it. Live with it.<br/>Make the harness finish the work.',M,y-29,CW,ParagraphStyle('cover2',fontName='Body',fontSize=18,leading=26,textColor=PAPER))
c.setStrokeColor(HexColor('#547369'));c.line(M,330,W-M,330)
for x,n,label in [(M,'500','acceptance scenarios'),(M+175,'25','areas of real life'),(M+345,'50','first-pass phone checks')]:
 c.setFillColor(GOLD);c.setFont('BodyBold',32);c.drawString(x,274,n)
 c.setFillColor(PAPER);c.setFont('Body',9);c.drawString(x,253,label)
para('The goal: less remembering, less chasing, less supervision.<br/>The evidence: useful outcomes, durable context and honest recovery.',M,209,CW,ParagraphStyle('c3',fontName='Body',fontSize=11,leading=17,textColor=PAPER))
para('FOR TONIGHT\n<br/>A working brief, a phone-first work order and an unexecuted test bank.<br/>Current baseline: iPhone 170 / Chrome extension 0.18.0.',M,124,CW,ParagraphStyle('c4',fontName='Body',fontSize=9.2,leading=15,textColor=HexColor('#d0ddd5')))
c.setFillColor(GOLD);c.setFont('Body',8);c.drawString(M,31,'07 SEPTEMBER 2026  |  CLOUDFlARE-BACKEND'.upper());c.drawRightString(W-M,31,'01')
c.showPage()

# 2. Intent and psychology
chrome('What making it perfect means');y=title('01 / Product standard','Make the burden leave their head.');y=body(sections['Your assignment'],y)
y=para('What good feels like',M,y-3,style=H2)-12
y=body(sections['What good feels like'],y,SMALL);c.showPage()
# 3. Known state
page('02 / Start from evidence','What is live. What is unproven.','The current starting point')
# 4. Architecture with vector handoff diagram
chrome('How the harness works');y=title('03 / Technical architecture','One task. Context across every hand.');y=para(markup(sections['How the harness works'].split('\n\n')[0]),M,y)-15
# Connected lanes; all labels describe functional roles, not success claims.
def box(x,top,w,h,head,sub,fill=white):
 c.setFillColor(fill);c.setStrokeColor(LINE);c.roundRect(x,top-h,w,h,8,fill=1,stroke=1)
 para(markup(head),x+10,top-11,w-20,ParagraphStyle('bh',fontName='BodyBold',fontSize=10.4,leading=13,textColor=INK))
 para(markup(sub),x+10,top-30,w-20,ParagraphStyle('bs',fontName='Body',fontSize=8.7,leading=11.5,textColor=MUTED))
box(M,y,CW,55,'01 Receive and understand','Phone transcript / app input / SendBlue text -> owner, speaker, time, event ID');y-=69
box(M,y,CW,61,'02 Context and one durable plan','Relevant conversation + quoted sources + owner memory -> model judgement -> task revision / dependencies / approval');y-=76
bw=(CW-24)/4
for i,(h,s) in enumerate([('Server','Research / compose'),('Connected API','Composio adapter'),('Paired Chrome','Observe / interact'),('iPhone','Native calendar')]):box(M+i*(bw+8),y,bw,57,h,s,PALE)
y-=72;box(M,y,CW,56,'03 Verify, remember and report','Read back the actual outcome -> receipt -> coherent app/text state -> close the right commitment');y-=73
for offset in [0]:
 y=para('<b>Memory:</b> owner-specific SQLite in Cloudflare Containers; R2 restore and snapshots. <b>Records:</b> Cloudflare API Worker and D1. Durable Object coordination manages owner runtimes. Old PocketBase-shaped routes are not proof of a PocketBase server.',M,y,style=SMALL)-13
example=sections['How the harness works'].split('Example: ',1)[1]
y=para('<b>Follow one quote:</b> '+markup(example),M,y,style=SMALL)-12
para('Source map: R5-R9, R12. This diagram explains the intended wired path; each deployment and user journey still needs its own proof.',M,y,style=SMALL);c.showPage()
# 5-12 operational pages
page('04 / Conversation contract','Text first means task continuity.','The text-first contract',
'Provider map: SendBlue messaging; Composio connected-app adapter; configurable model transports in brain/llm.py (including OpenRouter and Gemini); search capabilities in brain/research.py; Chrome extension execution; native EventKit calendar. Verify active credentials, account scope and model configuration rather than assuming a listed integration works.')
page('05 / Start on a real device','Use the app before editing it.','First hour: use the actual product')
page('06 / Generalistic reasoning','Fix the missing understanding.','Diagnose causes, not sentences')
page('07 / Tools and execution','A result has to exist somewhere.','Real tool completion')
page('08 / Overnight sequence','A finite plan for tonight.','Tonight\'s work order')
page('09 / Quality and measurement','Define success before claiming it.','Acceptance and release decision')
page('10 / Repository and release','Keep the shared codebase coherent.','Work safely in this repository')
page('11 / Morning handoff','Show what changed in real use.','What you hand back in the morning')
# 13. Clickable evidence
chrome('Evidence map');y=title('12 / References','Start here in the repository.','Pinned to 9039b83a unless the source describes an earlier dated release. Repository access may be required.')
refs=[
('R1','Harness laws and working rules','HARNESS-LAWS.md'),('R2','Current app readiness and known gaps','docs/CURRENT-APP-STATUS.md'),('R3','Fifteen-person lab: observations and limits','research/overnight-2026-09-07/persona-lab-status.md'),('R4','Reply-priority repair and release proof','research/overnight-2026-09-07/reply-priority-repair.md'),
('R5','Conversation -> brain -> task scheduling','brain/conversation.py'),('R6','Memory, quoted sources and task authority','brain/source_context.py'),('R7','API/browser routing and available capabilities','brain/hands.py'),('R8','SendBlue messaging and connection dispatch','migration/workers/src/messaging.ts'),('R9','Installed Chrome execution','extension/background.js'),('R10','Native calendar execution on iPhone','app/ios/Anticipy/Backend/NativeCalendarHand.swift'),('R11','Existing lab: reproduction and boundaries','proof/audit/persona_lab/README.md'),('R12','Per-owner runtime and snapshot lifecycle','brain/container_entry.py')]
for tag,label,path in refs:
 assert (ROOT/path).exists(),path
 url='https://github.com/anticipation-labs/Anticipy/blob/9039b83a/'+path
 y=para(f'<b>{tag}</b>  <link href="{url}" color="#24675b">{markup(label)}</link><br/><font size="8.5" color="#52675f">{markup(path)}</font>',M,y,style=SMALL)-9
# source-derived design summaries are short and cite these near the relevant section.
y=para('Design references',M,y-2,style=H2)-9
for tag,label,url in [('U1','Nielsen Norman Group - usability heuristics','https://www.nngroup.com/articles/ten-usability-heuristics/'),('U2','Microsoft Research - human-AI interaction','https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/'),('U3','Apple Human Interface Guidelines - feedback','https://developer.apple.com/design/human-interface-guidelines/feedback')]:
 y=para(f'{tag}  <link href="{url}" color="#24675b">{markup(label)}</link>',M,y,style=SMALL)-6
c.showPage()
# 14. Index and catalogue contract
chrome('500-scenario index');y=title('13 / Scenario catalogue','500 situations. One honest ledger.','New, proposed scenarios. All begin as NOT RUN. An expected result is a test contract, not a claim of existing capability.')
start_page=c.getPageNumber()+1
for idx,g in enumerate(groups):
 first=g['cases'][0]['id'];last=g['cases'][-1]['id'];pg=start_page+2*idx
 c.setFillColor(INK);c.setFont('BodyBold',8.5);c.drawString(M,y,g['number'])
 c.setFont('Body',9.1);c.drawString(M+23,y,g['title'])
 c.setFont('Body',8.6);c.setFillColor(MUTED);c.drawRightString(W-M-48,y,f'{first}-{last}')
 c.drawRightString(W-M,y,f'{pg}-{pg+1}')
 c.linkRect('',f'cat{g["number"]}',(M,y-3,W-M,y+11),relative=0,thickness=0)
 y-=18.6
 c.setStrokeColor(LINE);c.line(M,y+7,W-M,y+7)
y-=10
para('<b>How to use:</b> Read the setup above each category. Speak or type the request where indicated; reproduce interface actions on the actual phone. For fault drills, start from the phone/text path and inject the named downstream fault. Record simulation separately.<br/><br/><b>Smoke:</b> first two in each category (50). <b>Reserved:</b> last four (100), kept out of prompt-tuning examples until first evaluation. Use the editable CSV for actual results, evidence, latency, cost and retests. A polite unsupported response is still a capability gap when the promised outcome is missing.',M,y,style=SMALL)
c.showPage()

# 50 catalogue pages: two columns, five cases in each, clear source/expectation pairing.
for g in groups:
 for half in range(2):
  chrome(g['title'],True)
  if half==0:c.bookmarkPage('cat'+g['number']);c.addOutlineEntry(g['number']+'  '+g['title'],'cat'+g['number'],0,False)
  y=title(f'Catalogue {g["number"]} / {g["surface"]}',g['title'],g['setup'])
  top=min(y, H-151)
  card_h=(top-43-4*8)/5
  colw=(CW-18)/2
  for col in range(2):
   for row in range(5):
    case=g['cases'][half*10+col*5+row];x=M+col*(colw+18);t=top-row*(card_h+8);bottom=t-card_h
    c.setFillColor(white);c.setStrokeColor(LINE);c.roundRect(x,bottom,colw,card_h,7,fill=1,stroke=1)
    c.setFillColor(INK);c.setFont('BodyBold',8.7);c.drawString(x+11,t-16,'CASE '+case['id'])
    c.setFont('Body',7.7);c.setFillColor(MUTED);c.drawRightString(x+colw-11,t-16,case['set'].upper())
    yy=t-26
    p1=Paragraph('<b>Try:</b> '+markup(case['try']),CARD);_,h1=p1.wrap(colw-22,2000)
    p2=Paragraph('<b>Verify:</b> '+markup(case['expected']),CARD_EXPECT);_,h2=p2.wrap(colw-22,2000)
    needed=h1+h2+7
    assert yy-needed>=bottom+8,(case['id'],round(yy-needed-bottom,2),card_h)
    p1.drawOn(c,x+11,yy-h1);yy-=h1+7;p2.drawOn(c,x+11,yy-h2)
    layout_checks.append({'page':c.getPageNumber(),'case':case['id'],'clearance':round(yy-h2-bottom,2)})
  c.showPage()
c.save()
reader=PdfReader(str(OUT));texts=[p.extract_text() or '' for p in reader.pages]
all_text='\n'.join(texts)
for case in catalogue:assert len(re.findall(r'CASE '+case['id']+r'\b',all_text))==1,case['id']
assert '\ufffd' not in all_text
assert all(len(t.strip())>100 for t in texts)
qa={'pdf':str(OUT),'pages':len(reader.pages),'cases':len(catalogue),'categories':len(groups),'smoke':50,'reserved':100,'initial_status':'NOT RUN','page_specs':page_specs,'layout_checks':layout_checks,'min_case_clearance':min(x['clearance'] for x in layout_checks if 'case' in x),'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest()}
(ROOT/'tmp/pdfs/engineer-handoff/qa.json').write_text(json.dumps(qa,indent=2)+'\n')
print(json.dumps({k:v for k,v in qa.items() if k not in ['page_specs','layout_checks']},indent=2))
