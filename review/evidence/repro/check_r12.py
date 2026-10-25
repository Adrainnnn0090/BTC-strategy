"""Final bounded current-image code identity and payload-integrity check only."""
import hashlib,json,os,subprocess
from pathlib import Path

ROOT=Path('/workspace/BTC-strategy');OWN=Path('/workspace/BTCExpertReview/workspaces/repro')
IMAGE='sha256:79fcfc5131064b144d98bc625475b0a315bab53781c57a31ba3a28db0ec73640'
EXPECTED='c7439216d55207a9a480153d7555f6709817e70a'
DOCKER=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip();assert commit==EXPECTED
relative='provenance/release_manifest.json'
current=(ROOT/relative).read_bytes();frozen=subprocess.check_output(['git','-C',str(ROOT),'show',commit+':'+relative]);assert current==frozen
manifest=json.loads(current)
assert not any(Path(row['path']).parts[0]=='review' for row in manifest['files'])
code=r'''
import hashlib,json,os,sys
from importlib.metadata import distribution
from pathlib import Path
reads=set()
def guard(event,args):
 if event!='open'or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve()
 if p.is_relative_to('/research'):
  z=p.relative_to('/research').parts
  if z and z[0]=='review':raise AssertionError('real expert review excluded')
  if any(part.lower().startswith(('v01','v02'))for part in z):raise AssertionError('validation path excluded')
  if z and z[0]in('artifacts','models','training_inputs','data')and any('2026'in part for part in z):raise AssertionError('future economic path excluded')
  reads.add(str(p.relative_to('/research')))
sys.addaudithook(guard)
import btc_strategy
from btc_strategy.integrity import verify_integrity
package=Path(btc_strategy.__file__).resolve().parent
assert str(package).startswith('/usr/local/lib/python3.12/site-packages/')
source=Path('/research/src/btc_strategy')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
installed={str(p.relative_to(package)):digest(p)for p in package.rglob('*.py')}
mounted={str(p.relative_to(source)):digest(p)for p in source.rglob('*.py')}
assert installed==mounted,'installed Python package differs from frozen mounted source'
assert 'integrity.py'in installed and 'verify.py'in installed
assert not any(Path(path).exists()for path in('/workspace/BTCStrategyResearchLedger','/workspace/BinanceTradingRobot','/workspace/Polymarket_Arbitrage_Robot'))
integrity=verify_integrity();assert integrity['files']==886 and integrity['bytes']==56446427
dist=distribution('btc-strategy-research')
print(json.dumps(dict(status='PASS',installed_package=str(package),distribution_name=dist.metadata['Name'],distribution_version=dist.version,python_version=sys.version.split()[0],installed_python_file_count=len(installed),all_installed_python_bytes_equal_mounted_source=True,includes_current_integrity_and_verify_CLI=True,installed_code_hashes=installed,release_integrity=integrity,old_projects_visible=False,binance_robot_loaded=any(k.startswith('binance_robot')for k in sys.modules),review_files_opened=False,opened_repository_file_count=len(reads),model_prediction_or_native_replay=False,training_executed=False)),flush=True)
'''
name='btc-expert-repro-r12-'+str(os.getpid())
command=DOCKER+['run','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--memory','2g','--cpus','2','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(ROOT)+',dst=/research,readonly',IMAGE,'python','-I','-c',code]
completed=subprocess.run(command,capture_output=True,text=True,timeout=120)
with (OWN/'image-r12.log').open('x')as f:f.write(completed.stdout);f.write(completed.stderr)
container=json.loads(subprocess.check_output(DOCKER+['inspect',name],text=True))[0]
subprocess.run(DOCKER+['rm',name],check=True,capture_output=True,text=True)
receipt=json.loads(completed.stdout)if completed.returncode==0 else None
result={'round':12,'git_commit':commit,'manifest_sha256':hashlib.sha256(current).hexdigest(),'manifest_equals_frozen_git_blob':True,'declared_files':len(manifest['files']),'declared_bytes':sum(row['bytes']for row in manifest['files']),
 'image_id':IMAGE,'image_created':json.loads(subprocess.check_output(DOCKER+['image','inspect',IMAGE],text=True))[0]['Created'],
 'container_isolation':{'NetworkMode':container['HostConfig']['NetworkMode'],'ReadonlyRootfs':container['HostConfig']['ReadonlyRootfs'],'CapDrop':container['HostConfig']['CapDrop'],'SecurityOpt':container['HostConfig']['SecurityOpt'],'User':container['Config']['User'],'Mounts':[{'Source':row['Source'],'Destination':row['Destination'],'RW':row['RW']}for row in container['Mounts']]},
 'exit_code':completed.returncode,'actual_current_image_receipt':receipt,'stderr':completed.stderr,'prior_root_receipts_used_as_proof':False,'R10_36_native_books_repeated':False,'new_install_build_or_training':False,'other_review_contents_read':False,'source_or_shared_delivery_written':False}
with (OWN/'checks-r12.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
assert completed.returncode==0,completed.stderr
print(json.dumps({key:value for key,value in result.items()if key not in('actual_current_image_receipt','stderr')},ensure_ascii=False,indent=2))
print(json.dumps({key:value for key,value in receipt.items()if key!='installed_code_hashes'},ensure_ascii=False,indent=2))
