"""Unchanged README block with immediate private stream and status receipts."""
import os,re,sys,pathlib,tempfile,subprocess,time,json,ssl,socket,signal,hashlib,shutil
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
sys.path.insert(0,os.getcwd())
from tests.integration.test_gateway_tls import certificates
os.umask(0o077);root=pathlib.Path('/e/wheel-tests/inherited');mode=sys.argv[1];tree=pathlib.Path.cwd()
readme=(tree/'README.md').read_text();section=readme.split('### A2.2 网关配置与 HTTPS 启动',1)[1];block=re.search(r'```bash\n(.*?)\n```',section,re.S).group(1)
evidence=pathlib.Path(os.environ['A23_CLI_EVIDENCE']);parent=pathlib.Path(tempfile.mkdtemp(prefix='gateway-readme-',dir='/tmp'));parent.chmod(0o700);certificates(parent)
base=os.environ['AGENT_GUARD_TEST_DATABASE_URL'];names=[f'{mode}_gateway_readme_gw',f'{mode}_gateway_readme_ds']
with psycopg.connect(base,autocommit=True) as c:
 for name in names:c.execute('CREATE DATABASE '+name)
ds=[make_conninfo(**dict(conninfo_to_dict(base),dbname=n)) for n in names]
env=dict(os.environ,RUN_PRIVATE_PARENT=str(parent),RUN_GATEWAY_DSN=ds[0],RUN_DOWNSTREAM_DSN=ds[1],TLS_CERT_FILE=str(parent/'tls.pem'),TLS_KEY_FILE=str(parent/'tls.key'),PATH=str(pathlib.Path(sys.executable).parent)+':'+os.environ['PATH'])
status=evidence/'literal-shell-status.private.raw.log';hook=parent/'bash-status-hook';hook.write_text("trap 'printf \"%s\\t%s\\n\" \"$?\" \"$BASH_COMMAND\" >> \"$A23_SHELL_STATUS_LOG\"' DEBUG\n");hook.chmod(0o600);env.update(BASH_ENV=str(hook),A23_SHELL_STATUS_LOG=str(status))
out=evidence/'literal-stdout.private.raw.log';err=evidence/'literal-stderr.private.raw.log';fo=out.open('wb');fe=err.open('wb')
p=subprocess.Popen(['bash','-c',block],env=env,cwd=tree,stdout=fo,stderr=fe,start_new_session=True);assert os.getpgid(p.pid)==p.pid
child=None;ready=False;success=False;begin={'shell_pid':p.pid,'own_process_group':p.pid,'started':time.time(),'block_sha256':hashlib.sha256(block.encode()).hexdigest(),'readme_sha256':hashlib.sha256(readme.encode()).hexdigest(),'cwd':str(tree),'private_parent':str(parent),'private_runtime_parent_scope':'owned UID501 native container /tmp child 0700; literal block and assertions unchanged','stdout':str(out),'stderr':str(err)};(evidence/'literal-start.json').write_text(json.dumps(begin,indent=2))
try:
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  assert p.poll() is None,'README shell exited before TLS ready; actual streams preserved'
  inventory=subprocess.run(['/e/native/busybox','ps','-o','pid,ppid,args'],capture_output=True,text=True,check=True).stdout
  (evidence/'native-latest.private.raw.log').write_text(inventory)
  for row in inventory.splitlines()[1:]:
   fields=row.split(None,2)
   if len(fields)==3 and (fields[1]==str(p.pid) or fields[0]==str(p.pid)) and 'agent_guard.gateway' in fields[2] and 'run' in fields[2]:child=int(fields[0])
  try:
   ctx=ssl.create_default_context(cafile=str(parent/'ca.pem'))
   with socket.create_connection(('127.0.0.1',8444),timeout=.3) as s:
    with ctx.wrap_socket(s,server_hostname='gateway.agent-guard.test'):ready=True
   break
  except (OSError,ssl.SSLError):time.sleep(.05)
 assert ready and child is not None
 private_stats=[{'path':str(q),'uid':q.stat().st_uid,'mode':oct(q.stat().st_mode&0o777)} for q in [parent,parent/'gateway-demo',parent/'gateway-demo/config.json',parent/'gateway-demo/secrets.json',parent/'tls.key']]
 assert all(x['uid']==os.geteuid() and x['mode']==('0o700' if x['path'] in [str(parent),str(parent/'gateway-demo')] else '0o600') for x in private_stats)
 (evidence/'private-runtime-permissions.json').write_text(json.dumps(private_stats,indent=2))
 os.kill(child,signal.SIGINT);p.wait(timeout=15);fo.flush();fe.flush();stdout=out.read_text();stderr=err.read_text()
 assert p.returncode==0 and 'traceback' not in (stdout+stderr).lower()
 for d in ds:
  assert d not in stdout+stderr
  with psycopg.connect(d) as c:assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()==(0,)
 config=json.loads((parent/'gateway-demo/config.json').read_text());assert 'PRIVATE KEY' not in json.dumps(config)
 success=True;print('README_GATEWAY_LITERAL_PASS')
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGINT)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
 fo.close();fe.close()
 final={**begin,'ended':time.time(),'shell_exit':p.returncode,'gateway_pid':child,'tls_ca_hostname_verified':ready,'all_original_assertions_passed':success,'stdout_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256(err.read_bytes()).hexdigest(),'status_sha256':hashlib.sha256(status.read_bytes()).hexdigest() if status.exists() else None}
 (evidence/'literal-end.json').write_text(json.dumps(final,indent=2))
 with psycopg.connect(base,autocommit=True) as c:
  for name in names:c.execute('DROP DATABASE '+name)
 shutil.rmtree(parent)
