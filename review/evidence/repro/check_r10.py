"""One independent installed-package, network-none, read-only container replay."""
import json
import os
import subprocess
from pathlib import Path

OWN=Path('/workspace/BTCExpertReview/workspaces/repro')
ROOT=Path('/workspace/BTC-strategy')
DOCKER=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
name='btc-expert-repro-r10-'+str(os.getpid())
image='btc-strategy-audit:local'
code=r'''
import hashlib,json,os,runpy,sys
from pathlib import Path
reads=set()
def audit(event,args):
 if event!='open' or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve()
 if p.is_relative_to('/research'):
  z=p.relative_to('/research').parts
  if z and z[0]=='review':raise AssertionError('expert review files excluded from independent execution')
  if any(x.lower().startswith(('v01','v02'))for x in z):raise AssertionError('validation path forbidden')
  if z and z[0]in('artifacts','models','training_inputs','data') and any('2026'in x or '2027'in x for x in z):raise AssertionError('future economic path forbidden')
  reads.add(str(p.relative_to('/research')))
sys.addaudithook(audit)
import btc_strategy
package=Path(btc_strategy.__file__).resolve().parent
assert str(package).startswith('/usr/local/lib/python3.12/site-packages/'),str(package)
source=Path('/research/src/btc_strategy')
core=('artifacts.py','models.py','strategies.py','execution.py','costs.py','instrument.py','training.py')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
core_checks={name:{'installed_sha256':digest(package/name),'mounted_source_sha256':digest(source/name),'exact':digest(package/name)==digest(source/name)}for name in core}
runtime_checks={p.name:digest(p)==digest(source/'_runtime'/p.name)for p in(package/'_runtime').glob('*.py')}
assert all(v['exact']for v in core_checks.values()),'installed core differs from mounted frozen source'
assert all(runtime_checks.values()),'installed runtime differs from mounted frozen source'
installed_names={str(p.relative_to(package))for p in package.rglob('*.py')}
source_names={str(p.relative_to(source))for p in source.rglob('*.py')}
print(json.dumps(dict(type='independent_preflight',installed_package=str(package),core_checks=core_checks,runtime_files_compared=len(runtime_checks),runtime_all_exact=all(runtime_checks.values()),source_only_python_files=sorted(source_names-installed_names),installed_only_python_files=sorted(installed_names-source_names),python_version=sys.version.split()[0],cwd=str(Path.cwd()))),flush=True)
runpy.run_path('/research/scripts/verify_offline.py',run_name='__main__')
print(json.dumps(dict(type='independent_audit',research_files_opened=len(reads),review_files_opened=False,training_inputs_opened=any(p.startswith('training_inputs/')for p in reads),old_project_paths_visible=any(Path(p).exists()for p in('/workspace/BTCStrategyResearchLedger','/workspace/BinanceTradingRobot','/workspace/Polymarket_Arbitrage_Robot')),binance_robot_loaded=any(k.startswith('binance_robot')for k in sys.modules),read_paths=sorted(reads))),flush=True)
'''
command=DOCKER+['run','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','256','--cpus','2','--memory','4g','--tmpfs','/tmp:rw,nosuid,nodev,size=512m','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(ROOT)+',dst=/research,readonly',image,'python','-I','-c',code]
image_meta=json.loads(subprocess.check_output(DOCKER+['image','inspect',image],text=True))[0]
git_commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
git_status_before=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True)
log=OWN/'offline-r10.jsonl'
with log.open('x') as stream:
    try:
        completed=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,text=True,timeout=600)
        exit_code=completed.returncode;timed_out=False
    except subprocess.TimeoutExpired:
        subprocess.run(DOCKER+['stop','--time','1',name],capture_output=True,text=True)
        exit_code=None;timed_out=True
container=json.loads(subprocess.check_output(DOCKER+['inspect',name],text=True))[0]
host=container['HostConfig']
records=[];unparsed=[]
for line in log.read_text().splitlines():
    try:records.append(json.loads(line))
    except json.JSONDecodeError:unparsed.append(line)
preflight=next((row for row in records if row.get('type')=='independent_preflight'),None)
completion=next((row for row in records if row.get('type')=='completion'),None)
audit=next((row for row in records if row.get('type')=='independent_audit'),None)
models=[row for row in records if row.get('type')=='model']
accounts=[row for row in records if row.get('type')=='native']
git_status_after=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True)
result={'round':10,'git_commit_mounted':git_commit,'git_status_before':git_status_before,'git_status_after':git_status_after,
    'image_id':image_meta['Id'],'image_created':image_meta['Created'],'image_platform':image_meta['Os']+'/'+image_meta['Architecture'],
    'image_not_claimed_identical_to_commit':True,'container_name':name,'exit_code':exit_code,'timed_out':timed_out,
    'container_config':{'NetworkMode':host['NetworkMode'],'ReadonlyRootfs':host['ReadonlyRootfs'],'CapDrop':host['CapDrop'],'SecurityOpt':host['SecurityOpt'],'User':container['Config']['User'],'Mounts':[{'Type':m['Type'],'Source':m['Source'],'Destination':m['Destination'],'RW':m['RW']}for m in container['Mounts']],'PidsLimit':host['PidsLimit'],'Memory':host['Memory'],'NanoCpus':host['NanoCpus']},
    'preflight':preflight,'completion':completion,'independent_audit':audit,
    'actual_model_receipt_count':len(models),'actual_native_account_receipt_count':len(accounts),
    'all_six_models_exact':len(models)==6 and all(row['max_error']==0 and row['availability_exact'] for row in models),
    'all_36_native_complete_account_exact':len(accounts)==36 and all(row['complete_account_exact'] for row in accounts),
    'unparsed_output_lines':unparsed,'receipt_log':str(log),
    'existing_release_or_native_receipts_used_as_proof':False,'source_ledger_or_other_expert_content_read':False,
    'container_rebuilt':False,'dependency_installation_repeated':False,'trainer_or_strategy_search_executed':False,
    'limitations':['Existing image is older than the frozen commit and omits newer verification CLI; installed core/runtime bytes are compared explicitly rather than equating image and git objects.','This is a replay of consumed 2018–2025 inputs, not new validation or a refit.']}
with (OWN/'checks-r10.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
subprocess.run(DOCKER+['rm',name],check=True,capture_output=True,text=True)
print(json.dumps({key:result[key]for key in('git_commit_mounted','image_id','exit_code','timed_out','actual_model_receipt_count','actual_native_account_receipt_count','all_six_models_exact','all_36_native_complete_account_exact','completion','git_status_before','git_status_after','unparsed_output_lines')},ensure_ascii=False,indent=2))
