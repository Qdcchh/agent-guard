"""Exact current README AS shell with new owned DB, native PID, real CA/SAN and drain."""
import os,re,sys,pathlib,tempfile,subprocess,time,json,ssl,socket,signal,hashlib,shutil
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
sys.path.insert(0,os.getcwd())
import tests.integration.test_gateway_tls as cert_helper
root=pathlib.Path('/e/wheel-tests/inherited');mode=sys.argv[1];tree=pathlib.Path.cwd();readme=(tree/'README.md').read_text();section=readme.split('### 私有配置与开发 HTTPS',1)[1];block=re.search(r'```bash\n(.*?)\n```',section,re.S).group(1)
parent=pathlib.Path(tempfile.mkdtemp(prefix='as-readme-',dir='/tmp'));parent.chmod(0o700);cert_helper.HOST='as.agent-guard.test';cert_helper.certificates(parent)
base=os.environ['AGENT_GUARD_TEST_DATABASE_URL'];name=mode+'_as_readme_empty'
with psycopg.connect(base,autocommit=True) as c:c.execute('CREATE DATABASE '+name)
dsn=make_conninfo(**dict(conninfo_to_dict(base),dbname=name));env=dict(os.environ,RUN_PRIVATE_PARENT=str(parent),AGENT_GUARD_TEST_DATABASE_URL=dsn,TLS_CERT_FILE=str(parent/'tls.pem'),TLS_KEY_FILE=str(parent/'tls.key'),PATH=str(pathlib.Path(sys.executable).parent)+':'+os.environ['PATH'])
evidence=pathlib.Path(os.environ['A23_CLI_EVIDENCE']);status_log=evidence/'literal-shell-status.private.raw.log';hook=parent/'bash-status-hook';hook.write_text("trap 'printf \"%s\\t%s\\n\" \"$?\" \"$BASH_COMMAND\" >> \"$A23_SHELL_STATUS_LOG\"' DEBUG\n");hook.chmod(0o600);env['BASH_ENV']=str(hook);env['A23_SHELL_STATUS_LOG']=str(status_log)
os.umask(0o077);out=evidence/'literal-stdout.private.raw.log';err=evidence/'literal-stderr.private.raw.log';fo=out.open('wb');fe=err.open('wb')
p=subprocess.Popen(['bash','-c',block],env=env,cwd=tree,stdout=fo,stderr=fe,start_new_session=True);assert os.getpgid(p.pid)==p.pid;child=None;ready=False;success=False
begin={'mode':mode,'shell_pid':p.pid,'own_process_group':p.pid,'started':time.time(),'block_sha256':hashlib.sha256(block.encode()).hexdigest(),'readme_sha256':hashlib.sha256(readme.encode()).hexdigest(),'actual_private_parent':str(parent),'private_parent':'owned UID501 native /tmp child 0700'};(evidence/'literal-start.json').write_text(json.dumps(begin,indent=2))
try:
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  assert p.poll() is None,'literal AS shell exited before TLS readiness'
  inventory=subprocess.run(['/e/native/busybox','ps','-o','pid,ppid,args'],capture_output=True,text=True,check=True).stdout.splitlines()
  for row in inventory[1:]:
   fields=row.split(None,2)
   if len(fields)==3 and (fields[1]==str(p.pid) or fields[0]==str(p.pid)) and 'agent_guard.server' in fields[2] and 'run' in fields[2]:child=int(fields[0])
  try:
   ctx=ssl.create_default_context(cafile=str(parent/'ca.pem'))
   with socket.create_connection(('127.0.0.1',8443),timeout=.3) as s:
    with ctx.wrap_socket(s,server_hostname='as.agent-guard.test'):ready=True
   break
  except (OSError,ssl.SSLError):time.sleep(.05)
 assert ready and child is not None
 private_stats=[{'path':str(q),'uid':q.stat().st_uid,'mode':oct(q.stat().st_mode&0o777)} for q in [parent,parent/'as-demo',*(parent/'as-demo').iterdir(),parent/'tls.key']]
 assert all(x['uid']==os.geteuid() and x['mode']==('0o700' if x['path'] in [str(parent),str(parent/'as-demo')] else '0o600') for x in private_stats)
 (evidence/'private-runtime-permissions.json').write_text(json.dumps(private_stats,indent=2))
 os.kill(child,signal.SIGINT);p.wait(timeout=15);fo.flush();fe.flush();stdout=out.read_text();stderr=err.read_text();assert p.returncode==0;assert 'traceback' not in (stdout+stderr).lower();assert dsn not in stdout+stderr
 status_lines=status_log.read_text().splitlines();assert '0\tunset AGENT_GUARD_DATABASE_URL' in status_lines,status_lines
 with psycopg.connect(dsn) as c:assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()==(0,)
 for path in (parent/'as-demo').iterdir():
  assert path.stat().st_mode&0o777==0o600
 assert (parent/'as-demo').stat().st_mode&0o777==0o700
 inventory=subprocess.run(['/e/native/busybox','ps','-eo','pid,ppid,args'],capture_output=True,text=True,check=True).stdout
 assert not any(row.split() and row.split()[0]==str(child) for row in inventory.splitlines()[1:])
 (root/(mode+'-readme-AS-literal-observations.json')).write_text(json.dumps(dict(mode=mode,shell_pid=p.pid,AS_native_pid=child,exit=p.returncode,actual_server_command_exit=0,exit_evidence='DEBUG hook reads original previous status immediately before literal unset; script block bytes unchanged',shell_status_sha256=hashlib.sha256(status_log.read_bytes()).hexdigest(),block_sha256=hashlib.sha256(block.encode()).hexdigest(),readme_sha256=hashlib.sha256(readme.encode()).hexdigest(),tls_CA_SAN_verified=True,empty_database_unchanged=True,native_child_drained=True,private_dir700_all_files600=True,stdout=stdout,stderr=stderr),indent=2));success=True;print('README_AS_LITERAL_PASS')
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGINT)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
 fo.close();fe.close();(evidence/'literal-end.json').write_text(json.dumps({**begin,'ended':time.time(),'shell_exit':p.returncode,'AS_native_pid':child,'tls_CA_SAN_verified':ready,'all_original_assertions_passed':success,'stdout_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256(err.read_bytes()).hexdigest(),'status_sha256':hashlib.sha256(status_log.read_bytes()).hexdigest() if status_log.exists() else None},indent=2))
 with psycopg.connect(base,autocommit=True) as c:c.execute('DROP DATABASE '+name)
 shutil.rmtree(parent)
