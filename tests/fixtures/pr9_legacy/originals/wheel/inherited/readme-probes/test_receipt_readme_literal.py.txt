"""Current README three publisher commands, actual continuous PID and PG effects."""
import os,re,json,time,signal,subprocess,hashlib
from pathlib import Path
import psycopg
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.gateway.__main__ import init_config
from agent_guard.gateway.receipt_config import load_receipt_worker_config
from agent_guard.execution import store
from tests.fixtures.gateway import config_document
from tests.fixtures.receipts import full_state,publication_only
from tests.integration.test_receipt_publication import final_env

def test_readme_actual_three_commands_continuous_publish(ledger,dsn,downstream_dsn,tmp_path):
 env,op,_,_,_=final_env(dsn,downstream_dsn)
 before=full_state(dsn,downstream_dsn)
 private=tmp_path/'private';private.mkdir(mode=0o700)
 old=private/'gateway';init_config(old)
 document=config_document(env)
 (old/'config.json').write_bytes(canonical_json_bytes(document))
 original=(old/'config.json').read_bytes();secret=(old/'secrets.json').read_bytes()
 readme=Path('README.md').read_text().split('### A2.3 内部回执发布与真实 HTTPS 联合演示',1)[1]
 block=re.search(r'```sh\n(.*?)\n```',readme,re.S).group(1);lines=block.splitlines();assert len(lines)==3
 child=dict(os.environ,PRIVATE=str(private),OWNED_TEST_DSN=dsn,PATH=str(Path(os.sys.executable).parent)+':'+os.environ['PATH'])
 commands=[]
 for line in lines[:2]:
  p=subprocess.run(['bash','-c',line],env=child,capture_output=True,timeout=15)
  assert p.returncode==0
  assert b'PRIVATE KEY' not in p.stdout+p.stderr and dsn.encode() not in p.stdout+p.stderr
  commands.append(dict(command=line,exit=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode()))
 config=load_receipt_worker_config(private/'receipt/config.json');verifier=config.publisher(dsn)._verifier
 p=subprocess.Popen(['bash','-c',lines[2]],env=child,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 try:
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   assert p.poll() is None
   with psycopg.connect(dsn) as c:
    saved=store.fetch_outbox(c,op)
   if saved['receipt_status']=='READY':break
   time.sleep(.03)
  assert saved['receipt_status']=='READY'
  with psycopg.connect(dsn) as c:verifier.verify_tx(c,op,saved['receipt_jws'])
  publication_only(before,full_state(dsn,downstream_dsn))
  inventory=subprocess.run(['/e/native/busybox','ps','-o','pid,ppid,args'],capture_output=True,text=True,check=True).stdout.splitlines()
  children=[int(a[0]) for r in inventory[1:] if len(a:=r.split(None,2))==3 and a[1]==str(p.pid) and 'agent_guard.gateway.receipt_worker' in a[2]]
  actual=children[0] if children else p.pid
  os.kill(actual,signal.SIGINT);stdout,stderr=p.communicate(timeout=15)
  assert p.returncode==0 and dsn.encode() not in stdout+stderr and b'PRIVATE KEY' not in stdout+stderr
  commands.append(dict(command=lines[2],exit=p.returncode,shell_pid=p.pid,cli_pid=actual,stdout=stdout.decode(),stderr=stderr.decode()))
  assert (old/'config.json').read_bytes()==original and (old/'secrets.json').read_bytes()==secret
  record=dict(block_sha256=hashlib.sha256(block.encode()).hexdigest(),commands=commands,ready=True,independent_signature_verified=True,only_publication_fields_changed=True,old_config_secret_unchanged=True)
  Path(os.environ['A23_CLI_EVIDENCE'],'readme-literal.json').write_text(json.dumps(record,indent=2))
 finally:
  if p.poll() is None:p.kill();p.communicate(timeout=10)
