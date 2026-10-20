import os,pathlib,subprocess,json,sys
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
base=os.environ['AGENT_GUARD_TEST_DATABASE_URL'];mode=sys.argv[1];prefix=sys.argv[2];root=pathlib.Path('/e/source-tests/inherited')
records=[]
for flow in ['program','cli']:
 names=[f'{prefix}_{flow}_{role}' for role in ['gw','ds']]
 with psycopg.connect(base,autocommit=True) as c:
  for name in names:c.execute('CREATE DATABASE '+name)
 d=[make_conninfo(**dict(conninfo_to_dict(base),dbname=n)) for n in names]
 e=dict(os.environ,AGENT_GUARD_TEST_DATABASE_URL=d[0],AG_SMOKE_DOWNSTREAM_DSN=d[1],AGENT_GUARD_DATABASE_URL='')
 commands=[]
 if flow=='cli':
  for i in range(2):
   p=subprocess.run([sys.executable,'-m','agent_guard.ledger.migrate'],env=e,capture_output=True,text=True);assert p.returncode==0;commands.append(dict(command='migration',exit=p.returncode,stdout=p.stdout))
   assert ('001' in p.stdout) if i==0 else ('already up to date' in p.stdout)
 p=subprocess.run([sys.executable,str(root/'readme-snippet.py')],env=e,capture_output=True,text=True);assert p.returncode==0,p.stderr;assert 'SUCCEEDED' in p.stdout and 'ILLEGAL_TRANSITION' in p.stdout
 commands.append(dict(command='readme exact Python block',exit=p.returncode,stdout=p.stdout))
 with psycopg.connect(d[0]) as c:
  assert c.execute('SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants ORDER BY depth').fetchall()==[(0,70000,0,1)]*3
  assert c.execute('SELECT phase,count(*) FROM ag_ledger_events GROUP BY phase ORDER BY phase').fetchall()==[('RESERVE',1),('SETTLE',1)]
  assert c.execute('SELECT receipt_status,receipt_jws FROM ag_receipt_outbox').fetchall()==[('PENDING',None)]
 with psycopg.connect(d[1]) as c:assert c.execute('SELECT count(*) FROM ds_orders').fetchone()==(1,)
 records.append(dict(flow=flow,commands=commands,full_three_ancestor_counters=True,unique_order=True,unique_terminal=True,pending_unsigned=True))
 with psycopg.connect(base,autocommit=True) as c:
  for name in names:c.execute('DROP DATABASE '+name)
(root/(mode+'-readme-observations.json')).write_text(json.dumps(records,indent=2));print('BOTH_FLOWS_PASS')
