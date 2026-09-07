"""Summarize only SendBlue ingress status and fixed operational reason labels."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

raw=Path(sys.argv[1]).read_text(); decoder=json.JSONDecoder();position=0;observed=0
reasons={'secret mismatch':'secret_mismatch','secret missing':'secret_missing',
 'not configured':'not_configured','body is not a JSON object':'malformed_json',
 'wrong number':'wrong_destination','group message':'group_message',
 'message_handle missing':'missing_message_id','empty content':'empty_content',
 'outbound status update':'outbound_status'}
while position<len(raw):
 start=raw.find('{',position)
 if start<0:break
 try:event,end=decoder.raw_decode(raw,start)
 except ValueError:position=start+1;continue
 position=end
 if not isinstance(event,dict):continue
 wire=event.get('event') or {};request=wire.get('request') or {}
 if urlsplit(request.get('url','')).path!='/sms/sendblue':continue
 observed+=1;labels=[]
 for log in event.get('logs',[]):
  for message in log.get('message',[]):
   if not isinstance(message,str) or not message.startswith('sms/sendblue '):continue
   for phrase,label in reasons.items():
    if phrase in message:labels.append(label)
 print(json.dumps({'path':'/sms/sendblue','method':request.get('method'),
   'status':(wire.get('response') or {}).get('status'),'outcome':event.get('outcome'),
   'operational_reasons':sorted(set(labels))}))
print(json.dumps({'sendblue_requests_observed':observed}))
