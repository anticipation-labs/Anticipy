"""Start a dedicated loopback Worker/D1 fixture. Never deploys to Cloudflare."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]

def main():
    p=argparse.ArgumentParser();p.add_argument('--node',default='node');a=p.parse_args()
    state=ROOT/'work/audit/persona-lab';state.mkdir(parents=True,exist_ok=True)
    config=state/'wrangler.json'
    config.write_text(json.dumps({'name':'anticipy-persona-lab',
        'main':str(ROOT/'migration/workers/src/index.ts'),
        'compatibility_date':'2026-09-03','compatibility_flags':['nodejs_compat'],
        'd1_databases':[{'binding':'DB','database_name':'persona-lab',
                         'database_id':'00000000-0000-4000-8000-000000000088'}],
        'durable_objects':{'bindings':[{'name':'PAIR_CODE_COUNTER','class_name':'PairCodeCounter'}]},
        'migrations':[{'tag':'v1','new_sqlite_classes':['PairCodeCounter']}],
        'vars':{'ANTICIPY_SERVICE_TOKEN':'persona-lab-local-only',
                'ANTICIPY_AUTH_SECRET':'persona-lab-auth-secret-no-production-access','ANTICIPY_ENV':'test'}},indent=2))
    wrangler=[a.node,str(ROOT/'migration/workers/node_modules/wrangler/bin/wrangler.js')]
    flags=['--local','--config',str(config),'--persist-to',str(state/'d1')]
    subprocess.run(wrangler+['d1','execute','persona-lab',*flags,'--file',str(ROOT/'migration/d1/schema.sql')],cwd=ROOT,check=True)
    subprocess.run(wrangler+['dev',*flags,'--ip','127.0.0.1','--port','8788'],cwd=ROOT,check=True)

if __name__=='__main__':main()
