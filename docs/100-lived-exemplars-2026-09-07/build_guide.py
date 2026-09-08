"""Create a readable exemplar guide. These examples are not executed test results."""
from pathlib import Path
import json, html, re, hashlib
import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from pypdf import PdfReader

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'output/pdf/Anticipy-in-real-life-100-conversation-exemplars.pdf'
TMP=ROOT/'tmp/pdfs/100-lived-exemplars'
OUT.parent.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True)
fonts=Path(reportlab.__file__).parent/'fonts'
for n,f in [('Body','Vera.ttf'),('Bold','VeraBd.ttf'),('Italic','VeraIt.ttf')]:pdfmetrics.registerFont(TTFont(n,str(fonts/f)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
W,H=A4;M=42;CW=W-2*M
INK=HexColor('#182f36');PAPER=HexColor('#f7f3eb');ACCENT=HexColor('#9c5734');MUTED=HexColor('#5a6b68');LINE=HexColor('#d6deda');GREEN=HexColor('#2b6453')
STYLE=ParagraphStyle('normal',fontName='Body',fontSize=11,leading=16,textColor=INK)
SMALL=ParagraphStyle('small',parent=STYLE,fontSize=9.4,leading=12.5)
TEXT=ParagraphStyle('text',parent=STYLE,fontSize=10.8,leading=14.5)
DETAIL=ParagraphStyle('detail',parent=TEXT,fontSize=10.3,leading=14.0,textColor=MUTED)
ANSWER=ParagraphStyle('answer',parent=TEXT,textColor=GREEN)

def esc(s):
 for a,b in [('—','-'),('–','-'),('’',"'"),('“','"'),('”','"')]:s=s.replace(a,b)
 return html.escape(s)

sections={}
for block in (HERE/'guide.md').read_text().split('\n## ')[1:]:
 k,v=block.split('\n',1);sections[k]=v.strip()
groups=[];cases=[]
for g in (HERE/'exemplars.txt').read_text().split('# ')[1:]:
 heading,rest=g.split('\n',1);number,name=heading.split(' | ')
 records=[]
 for b in rest.strip().split('\n\n'):
  lines=b.splitlines();ident,title,person,mode=lines[0].split(' | ')
  d={'id':ident,'title':title,'person':person,'mode':mode,'category':name}
  for l in lines[1:]:k,v=l.split(': ',1);d[k.lower()]=v
  assert set(['memory','heard','response','work','carry','flip']).issubset(d)
  records.append(d);cases.append(d)
 assert len(records)==10
 groups.append({'number':number,'name':name,'cases':records})
assert len(cases)==100 and [x['id'] for x in cases]==[f'{i:03}' for i in range(1,101)]
assert len({x['heard'] for x in cases})==100
(HERE/'exemplars.json').write_text(json.dumps({'kind':'Fictional worked exemplars of intended behavior; not executed tests','cases':cases},ensure_ascii=False,indent=2)+'\n')
c=canvas.Canvas(str(OUT),pagesize=A4,pageCompression=1)
c.setTitle('Anticipy in real life | 100 conversation exemplars')
c.setAuthor('Anticipy')
c.setSubject('A replacement customer-experience guide: proactive transcripts, memory, real tools and verified outcomes')
checks=[]

def para(text,x,y,width=CW,style=STYLE):
 p=Paragraph(text,style);_,h=p.wrap(width,3000)
 assert y-h>38,(c.getPageNumber(),round(y-h,2),text[:60])
 p.drawOn(c,x,y-h);return y-h

def header(label,example=False):
 c.setFillColor(PAPER);c.rect(0,0,W,H,fill=1,stroke=0)
 c.setFillColor(INK);c.setFont('Bold',9);c.drawString(M,H-29,'ANTICIPY / IN REAL LIFE')
 c.setFillColor(MUTED);c.setFont('Body',8);c.drawRightString(W-M,H-29,label.upper())
 c.setStrokeColor(LINE);c.line(M,H-42,W-M,H-42)
 c.setFont('Body',7.6);c.drawString(M,23,'FICTIONAL EXEMPLARS / INTENDED BEHAVIOR' if example else 'UNDERSTAND THE PERSON. CARRY THE CONTEXT. FINISH THE WORK.')
 c.drawRightString(W-M,23,f'{c.getPageNumber():02}')
 c.bookmarkPage('page'+str(c.getPageNumber()))

def title(kicker,t,sub=''):
 c.setFillColor(ACCENT);c.setFont('Bold',9);c.drawString(M,H-68,kicker.upper())
 y=para(esc(t),M,H-79,style=ParagraphStyle('h',fontName='Bold',fontSize=27,leading=32,textColor=INK))
 if sub:y=para(esc(sub),M,y-13,style=SMALL)
 return y-20

def prose(key,y,style=STYLE):
 for p in sections[key].split('\n\n'):y=para(esc(p),M,y,style=style)-13
 return y

# Cover
c.setFillColor(INK);c.rect(0,0,W,H,fill=1,stroke=0)
c.setFillColor(HexColor('#e7b886'));c.setFont('Bold',15);c.drawString(M,H-69,'Anticipy')
para('In real life.',M,H-151,style=ParagraphStyle('cover',fontName='Bold',fontSize=48,leading=55,textColor=PAPER))
para('100 conversations that show<br/>what the product is for.',M,H-237,style=ParagraphStyle('sub',fontName='Body',fontSize=22,leading=30,textColor=PAPER))
c.setStrokeColor(HexColor('#52726f'));c.line(M,395,W-M,395)
para('A plan forming over dinner.<br/>A promise buried in a meeting.<br/>A useful answer after an interruption.<br/>A task that actually gets finished.',M,362,style=ParagraphStyle('list',fontName='Body',fontSize=15,leading=25,textColor=PAPER))
para('For the engineer: use it like a customer.<br/>Test it. Fix what fails. Ship the verified experience.',M,194,style=ParagraphStyle('call',fontName='Bold',fontSize=12,leading=19,textColor=HexColor('#e7b886')))
para('Replacement guide. No work schedule or points system.<br/>These are fictional worked examples, not completed test results.',M,107,style=ParagraphStyle('note',fontName='Body',fontSize=9.3,leading=14,textColor=HexColor('#c8d6d1')))
c.setFont('Body',8);c.drawString(M,30,'CONVERSATION / MEMORY / TOOLS / OUTCOMES');c.drawRightString(W-M,30,'01');c.showPage()

# Product explanation
header('The idea');y=title('The product in plain language','Less work in your head.');y=prose('What Anticipy is',y)
y=para('Hear a situation. Carry its context. Bring back useful work.',M,y-9,style=ParagraphStyle('callout',fontName='Bold',fontSize=18,leading=24,textColor=GREEN))-19
y=para('A good result may be a finished comparison, a verified calendar change, a private draft, one precise missing question or the decision to stay quiet. The user should recognize the situation and know what happens next.',M,y)-17
para('This guide replaces the earlier timed brief as the explanation of the intended experience. The previous 500-case catalogue remains optional engineering reference material; this book is about understanding and building the product.',M,y,style=SMALL)
c.showPage()

# Technical shape
header('The harness');y=title('One general system','The same brain, different tools.');y=prose('One general system',y)
nodes=[('Conversation + memory','Owner, speaker, source, time, current facts and unresolved work'),('Contextual model + durable task','Meaning, useful next action, missing details, task revision and authority'),('Available tools + verified outcome','API / paired Chrome / server / supported phone action -> evidence -> answer')]
for h,s in nodes:
 c.setFillColor(white);c.setStrokeColor(LINE);c.roundRect(M,y-56,CW,56,7,fill=1,stroke=1)
 para('<b>'+esc(h)+'</b>',M+12,y-10,CW-24,SMALL);para(esc(s),M+12,y-28,CW-24,SMALL);y-=67
para('Meaning belongs to the model with context. Structural checks enforce identity, permissions, valid tool arguments and actual effects. The examples are not a phrase classifier, a library of canned answers or 100 separate programmed workflows.',M,y-1,style=SMALL)
c.showPage()

# Index
header('Find a situation');y=title('Read across lives','100 exemplars. Ten parts of life.');y=prose('How to read the exemplars',y,SMALL)-7
for i,g in enumerate(groups):
 first=g['cases'][0]['id'];last=g['cases'][-1]['id'];pg=5+i*5
 c.setFillColor(INK);c.setFont('Bold',10);c.drawString(M,y,g['name'])
 c.setFillColor(MUTED);c.setFont('Body',9);c.drawRightString(W-M,y,f'{first}-{last}  /  pp. {pg}-{pg+4}')
 c.linkRect('',f'group{g["number"]}',(M,y-4,W-M,y+13),relative=0,thickness=0)
 c.setStrokeColor(LINE);c.line(M,y-10,W-M,y-10);y-=32
para('The instruction to the engineer follows the exemplars on pages 55-56. Use the conversations to understand the product, then use the actual app and fix what reality reveals.',M,y-5,style=SMALL)
c.showPage()

# Two detailed, full-width conversations per page.
labels={'memory':'Before','heard':'Conversation','response':'Anticipy','work':'Behind the response','carry':'Remembers','flip':'When the context changes'}
for g in groups:
 for pair in range(5):
  header('Conversation exemplars',True)
  if pair==0:
   c.bookmarkPage('group'+g['number']);c.addOutlineEntry(g['name'],'group'+g['number'],0,False)
  c.setFillColor(ACCENT);c.setFont('Bold',9);c.drawString(M,H-65,g['number']+' / '+g['name'].upper())
  top=H-80;gap=12;cardh=(top-43-gap)/2
  for j,d in enumerate(g['cases'][pair*2:pair*2+2]):
   t=top-j*(cardh+gap);b=t-cardh;x=M+13;cw=CW-26
   c.setFillColor(white);c.setStrokeColor(LINE);c.roundRect(M,b,CW,cardh,8,fill=1,stroke=1)
   y=para(d['id']+' / '+esc(d['title']),x,t-12,cw,ParagraphStyle('caseh',fontName='Bold',fontSize=14,leading=17,textColor=INK))-5
   y=para(esc(d['person'])+'  |  '+esc(d['mode'].lower()),x,y,cw,ParagraphStyle('casep',parent=SMALL,fontSize=9.0,leading=11.8,textColor=ACCENT))-7
   for key in ['memory','heard','response','work','carry','flip']:
    st=ANSWER if key=='response' else (TEXT if key=='heard' else DETAIL)
    value=esc(d[key]).replace(' // ','<br/>')
    rendered=('<b>What happens next</b><br/>'+value) if key=='response' else ('<b>'+labels[key]+':</b> '+value)
    y=para(rendered,x,y,cw,st)-5
   clearance=y+5-b
   assert clearance>=9,(d['id'],round(clearance,2))
   checks.append({'case':d['id'],'page':c.getPageNumber(),'bottom_clearance':round(clearance,2)})
  c.showPage()

# A simple instruction, without a schedule or scorecard.
header('To the engineer');y=title('Use it. Fix it. Ship it.','Live the experience yourself.');y=prose('To the engineer: use it, fix it, ship it',y)
c.showPage()
header('Repository references');y=title('Finish on the actual product','Keep the release honest.');y=prose('Repository and release essentials',y,SMALL)
y=para('<b>Repository starting points</b>',M,y-4,style=STYLE)-15
refs=[('Working laws and contextual reasoning','HARNESS-LAWS.md'),('Task interpretation','brain/conversation.py'),('Quoted context across hands','brain/source_context.py'),('Owner memory','brain/memory.py'),('Tool routing and execution','brain/hands.py'),('SendBlue transport','migration/workers/src/messaging.ts'),('Paired Chrome execution','extension/background.js'),('Dated readiness evidence and remaining gaps','docs/CURRENT-APP-STATUS.md')]
for label,path in refs:
 assert (ROOT/path).exists(),path
 url='https://github.com/anticipation-labs/Anticipy/blob/9039b83a/'+path
 y=para('<link href="'+url+'" color="#2b6453">'+esc(label)+'</link>  <font size="8">'+esc(path)+'</font>',M,y,style=SMALL)-10
para('References are pinned to the previously recorded source snapshot. Inspect the current cloudflare-backend branch and live system before changing or claiming a release. This document does not assert universal reliability, 500 working integrations or new live-test results.',M,y-8,style=SMALL)
c.showPage();c.save()
r=PdfReader(OUT);assert len(r.pages)==56,len(r.pages)
text='\n'.join(p.extract_text() or '' for p in r.pages)
for d in cases:assert len(re.findall(r'\b'+d['id']+r' / ',text))==1,d['id']
assert '\ufffd' not in text
assert '00:00-' not in text
qa={'scope':'Document QA only; fictional exemplars have not been run','pages':len(r.pages),'examples':100,'categories':10,'unique_conversations':len({d['heard'] for d in cases}),'min_card_clearance':min(x['bottom_clearance'] for x in checks),'case_layout':checks,'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest()}
(TMP/'qa.json').write_text(json.dumps(qa,indent=2)+'\n')
print(json.dumps({k:v for k,v in qa.items() if k!='case_layout'},indent=2))
