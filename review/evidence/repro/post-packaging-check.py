"""Append-only packaging verification from a clean Git clone; no research round."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path

SOURCE=Path('/workspace/BTC-strategy');OWN=Path('/workspace/BTCExpertReview/workspaces/repro')
COMMIT='57205cb9935093afec6a80ae1972c22dce4ab55d'
R12='c7439216d55207a9a480153d7555f6709817e70a'
IMAGE='sha256:79fcfc5131064b144d98bc625475b0a315bab53781c57a31ba3a28db0ec73640'
DOCKER=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
original_reports={f'r{round:02d}.json':digest(OWN/f'r{round:02d}.json')for round in range(1,13)}
with tempfile.TemporaryDirectory(prefix='btc-repro-post-packaging-')as temporary:
 clone=Path(temporary)/'clean-clone'
 clone_result=subprocess.run(['git','clone','--no-local','--no-hardlinks','--no-checkout',str(SOURCE),str(clone)],capture_output=True,text=True,check=True)
 checkout=subprocess.run(['git','-C',str(clone),'checkout','--detach',COMMIT],capture_output=True,text=True,check=True)
 assert subprocess.check_output(['git','-C',str(clone),'rev-parse','HEAD'],text=True).strip()==COMMIT
 status_before=subprocess.check_output(['git','-C',str(clone),'status','--porcelain'],text=True)
 assert not status_before
 tracked=set(subprocess.check_output(['git','-C',str(clone),'ls-files','-z'],text=True).split('\0'))
 path='provenance/release_manifest.json';raw=(clone/path).read_bytes();manifest=json.loads(raw)
 committed=subprocess.check_output(['git','-C',str(clone),'show',COMMIT+':'+path]);assert raw==committed
 previous=json.loads(subprocess.check_output(['git','-C',str(clone),'show',R12+':'+path]))
 old={row['path']:row for row in previous['files']};new={row['path']:row for row in manifest['files']}
 removed=sorted(set(old)-set(new))
 all_remaining_identical=all(row==old[name]for name,row in new.items())
 assert len(new)==881 and len(removed)==5 and all_remaining_identical
 assert all(any(part.endswith(('.egg-info','.dist-info'))for part in Path(name).parts)for name in removed)
 assert all(name in tracked for name in new)
 metadata_dirs=[str(p.relative_to(clone))for p in clone.rglob('*')if '.git'not in p.relative_to(clone).parts and p.is_dir()and p.name.endswith(('.egg-info','.dist-info'))]
 assert not metadata_dirs
 code=r'''
import hashlib,json,os,runpy,sys
from pathlib import Path
reads=set()
def audit(event,args):
 if event!='open'or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve()
 if p.is_relative_to('/research'):
  z=p.relative_to('/research').parts
  if z and z[0]=='review':raise AssertionError('real review content excluded; --review is not authorized')
  if any(part.lower().startswith(('v01','v02'))for part in z):raise AssertionError('validation path excluded')
  if z and z[0]in('artifacts','models','training_inputs','data')and any('2026'in part for part in z):raise AssertionError('future economic path excluded')
  reads.add(str(p.relative_to('/research')))
sys.addaudithook(audit)
import btc_strategy
package=Path(btc_strategy.__file__).resolve().parent
assert str(package).startswith('/usr/local/lib/python3.12/site-packages/')
source=Path('/research/src/btc_strategy');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
installed={str(p.relative_to(package)):sha(p)for p in package.rglob('*.py')}
mounted={str(p.relative_to(source)):sha(p)for p in source.rglob('*.py')}
assert installed==mounted
assert not any(Path(p).exists()for p in('/workspace/BTCStrategyResearchLedger','/workspace/BinanceTradingRobot','/workspace/Polymarket_Arbitrage_Robot'))
print(json.dumps(dict(type='packaging_preflight',installed_package=str(package),installed_python_files=len(installed),all_installed_python_bytes_equal_clean_clone=True,old_projects_visible=False,installed_code_hashes=installed)),flush=True)
sys.argv=['btc_strategy.verify','--integrity']
runpy.run_module('btc_strategy.verify',run_name='__main__')
print(json.dumps(dict(type='packaging_audit',review_files_opened=False,review_gate_executed=False,model_prediction_executed=False,native_replay_executed=False,training_executed=False,binance_robot_loaded=any(k.startswith('binance_robot')for k in sys.modules),opened_clone_file_count=len(reads))),flush=True)
'''
 name='btc-repro-post-packaging-'+str(os.getpid())
 command=DOCKER+['run','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--memory','2g','--cpus','2','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(clone)+',dst=/research,readonly',IMAGE,'python','-I','-c',code]
 run=subprocess.run(command,capture_output=True,text=True,timeout=120)
 with (OWN/'post-packaging-container.jsonl').open('x')as stream:stream.write(run.stdout);stream.write(run.stderr)
 inspected=json.loads(subprocess.check_output(DOCKER+['inspect',name],text=True))[0]
 subprocess.run(DOCKER+['rm',name],capture_output=True,text=True,check=True)
 assert run.returncode==0,run.stderr
 rows=[json.loads(line)for line in run.stdout.splitlines()]
 preflight=next(row for row in rows if row.get('type')=='packaging_preflight')
 integrity=next(row for row in rows if row.get('scope','').startswith('Content equality'))
 audit=next(row for row in rows if row.get('type')=='packaging_audit')
 assert integrity['status']=='PASS'and integrity['files']==881 and integrity['bytes']==sum(row['bytes']for row in new.values())
 status_after=subprocess.check_output(['git','-C',str(clone),'status','--porcelain'],text=True);assert not status_after
 report_hashes_after={name:digest(OWN/name)for name in original_reports}
 result={'phase':'post_review_packaging','candidate_commit':COMMIT,'R12_commit':R12,'image_id':inspected['Image'],
  'clone_command':['git','clone','--no-local','--no-hardlinks','--no-checkout',str(SOURCE),'<private_tmp>/clean-clone'],
  'detached_checkout_commit':COMMIT,'clone_git_status_before':status_before,'clone_git_status_after':status_after,
  'clone_install_metadata_directories':metadata_dirs,'release_manifest_sha256':hashlib.sha256(raw).hexdigest(),'release_manifest_equals_frozen_git_blob':raw==committed,
  'payload_count':len(new),'payload_bytes':sum(row['bytes']for row in new.values()),'all_881_payloads_Git_tracked':all(name in tracked for name in new),
  'removed_install_metadata_paths':removed,'all_881_remaining_rows_hash_bytes_unchanged_from_R12':all_remaining_identical,
  'container_exit_code':run.returncode,'container_isolation':{'NetworkMode':inspected['HostConfig']['NetworkMode'],'ReadonlyRootfs':inspected['HostConfig']['ReadonlyRootfs'],'CapDrop':inspected['HostConfig']['CapDrop'],'SecurityOpt':inspected['HostConfig']['SecurityOpt'],'User':inspected['Config']['User'],'Mounts':[{'Source':m['Source'],'Destination':m['Destination'],'RW':m['RW']}for m in inspected['Mounts']]},
  'actual_container_preflight':preflight,'actual_integrity_CLI_receipt':integrity,'actual_container_audit':audit,
  'original_12_report_hashes_before':original_reports,'original_12_report_hashes_after':report_hashes_after,'original_12_reports_unchanged':original_reports==report_hashes_after,
  'review_gate_executed':False,'other_role_review_contents_read':False,'new_market_samples':0,'training_or_36_replay_executed':False,
  'clean_clone_and_container_deleted_after_checks':True,'CI_failure_independently_reproduced':False,
  'qualification':'Packaging appendix only: R12 verified a working-tree manifest including generated install metadata. This check verifies a clean Git checkout with only the five generated metadata entries removed; all previous reports and CI failure history remain intact.'}
 with (OWN/'post-packaging-checks.json').open('x')as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
 print(json.dumps({key:result[key]for key in('phase','candidate_commit','image_id','payload_count','payload_bytes','all_881_payloads_Git_tracked','removed_install_metadata_paths','all_881_remaining_rows_hash_bytes_unchanged_from_R12','container_exit_code','actual_integrity_CLI_receipt','actual_container_audit','original_12_reports_unchanged','review_gate_executed','new_market_samples')},ensure_ascii=False,indent=2))
