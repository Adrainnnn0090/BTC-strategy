"""Post-review packaging verification through selected Git objects and private index."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT=Path('/workspace/BTC-strategy')
OLD='c7439216d55207a9a480153d7555f6709817e70a'
NEW='57205cb9935093afec6a80ae1972c22dce4ab55d'
OUTPUT=Path('/workspace/BTCExpertReview/workspaces/data/post-packaging-checks.json')


def git(*arguments):
    return subprocess.check_output(['git','-C',str(ROOT),*arguments],text=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(commit):
    raw=subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-r','--long','-z',commit])
    result={}
    for record in raw.split(b'\0'):
        if not record:continue
        header,path=record.split(b'\t',1)
        mode,kind,object_id,size=header.decode().split()
        result[path.decode()]=dict(mode=mode,kind=kind,object_id=object_id,bytes=None if size=='-' else int(size))
    return result


assert git('rev-parse','HEAD').strip()==NEW
old_manifest=json.loads(git('show',OLD+':provenance/release_manifest.json'))
new_manifest=json.loads(git('show',NEW+':provenance/release_manifest.json'))
old_records={item['path']:item for item in old_manifest['files']}
records={item['path']:item for item in new_manifest['files']}
assert len(old_records)==886 and len(records)==881
assert sum(item['bytes'] for item in records.values())==56437576
removed=sorted(set(old_records)-set(records))
assert len(removed)==5 and not set(records)-set(old_records)
assert all(records[path]==old_records[path] for path in records)
assert all(any(part.endswith('.egg-info') for part in Path(path).parts) for path in removed)
old_tree,new_tree=tree(OLD),tree(NEW)
tracked=set(git('ls-files','-z').split('\0'))
assert set(records)<=tracked and set(records)<=set(new_tree)
assert all(path not in old_tree and path not in new_tree and path not in tracked for path in removed)
assert all(new_tree[path]==old_tree[path] and new_tree[path]['kind']=='blob' and new_tree[path]['bytes']==records[path]['bytes'] for path in records)
economic_roots=('src/','models/','artifacts/','training_inputs/','strategies/')
old_economic={path:value for path,value in old_tree.items() if path.startswith(economic_roots)}
new_economic={path:value for path,value in new_tree.items() if path.startswith(economic_roots)}
assert old_economic==new_economic
assert not git('diff','--name-only',NEW,'--',*[root.rstrip('/') for root in economic_roots]).strip()
source_index=ROOT/'.git/index'
source_index_hash=sha(source_index)
prior_r12=Path('/workspace/BTCExpertReview/workspaces/data/r12.json')
prior_r12_hash=sha(prior_r12)

# Materialize only release payload, its manifest, and the packaging generator.
# A private index prevents any original .git/index mutation and excludes review content.
temporary=Path(tempfile.mkdtemp(prefix='btc-data-post-packaging-'))
checkout=temporary/'checkout';checkout.mkdir()
private_index=temporary/'private-index'
selected=sorted(set(records)|{'scripts/make_manifest.py','provenance/release_manifest.json'})
assert not any(path.startswith(('review/','verification/')) for path in selected)
index_info=''.join(f"{new_tree[path]['mode']} {new_tree[path]['object_id']}\t{path}\n" for path in selected)
env=os.environ.copy()
env.update(GIT_DIR=str(ROOT/'.git'),GIT_WORK_TREE=str(checkout),GIT_INDEX_FILE=str(private_index),GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
index_run=subprocess.run(['git','-c','core.splitIndex=false','update-index','--index-info'],input=index_info,text=True,capture_output=True,env=env,cwd=checkout)
assert index_run.returncode==0,index_run.stderr
checkout_run=subprocess.run(['git','checkout-index','--all','--force','--prefix='+str(checkout)+'/'],text=True,capture_output=True,env=env,cwd=checkout)
assert checkout_run.returncode==0,checkout_run.stderr
checked_bytes=0
for relative,item in records.items():
    path=checkout/relative
    assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
    checked_bytes+=path.stat().st_size
assert checked_bytes==56437576


def generate():
    return subprocess.run([os.sys.executable,str(checkout/'scripts/make_manifest.py')],text=True,capture_output=True,env=env,cwd=checkout)


baseline=generate()
assert baseline.returncode==0,baseline.stderr
generated_path=checkout/'provenance/release_manifest.json'
assert json.loads(generated_path.read_text())==new_manifest
baseline_hash=sha(generated_path)
fake=checkout/'src/synthetic-untracked.egg-info/SOURCES.txt'
fake.parent.mkdir(parents=True)
fake.write_text('Controlled fake generated packaging metadata, not research data.\n')
with_fake=generate()
assert with_fake.returncode==0,with_fake.stderr
assert sha(generated_path)==baseline_hash
assert not any('.egg-info' in part or '.dist-info' in part for row in json.loads(generated_path.read_text())['files'] for part in Path(row['path']).parts)
untracked_research=checkout/'src/synthetic-untracked-research-input.json'
untracked_research.write_text('{"synthetic":true}\n')
negative=generate()
assert negative.returncode!=0
assert 'Stage intended payload before freezing: src/synthetic-untracked-research-input.json' in negative.stderr
assert sha(generated_path)==baseline_hash
untracked_research.unlink()
assert sha(source_index)==source_index_hash and sha(prior_r12)==prior_r12_hash
assert git('rev-parse','HEAD').strip()==NEW

result=dict(phase='post_review_packaging',role='data',status='PASS_BOUNDED',candidate_git=NEW,baseline_git=OLD,
            manifest=dict(old_count=886,new_count=881,verified_clean_git_object_bytes=checked_bytes,
                          retained_records_identical=True,all_current_entries_tracked=True,
                          all_clean_payload_sha256_and_sizes_match=True,
                          removed=[old_records[path] for path in removed],
                          removed_records_were_untracked_at_both_commits=True),
            original_economic_code_models_raw_data_training_inputs_and_accounts_git_objects_unchanged=True,
            clean_materialization=dict(path=str(checkout),method='Selected committed Git blobs checked out with a private GIT_INDEX_FILE; no review/verification files materialized.',
                                       baseline_generator_exact=True,synthetic_egg_info_does_not_enter_manifest=True,
                                       ordinary_untracked_research_input_rejected=True,
                                       negative_expected_return_code=negative.returncode,
                                       negative_error='Stage intended payload before freezing: src/synthetic-untracked-research-input.json',
                                       rejected_generation_did_not_change_prior_manifest=True),
            original_candidate_index_sha256_preserved=source_index_hash,original_r12_sha256_preserved=prior_r12_hash,
            limitations=['This is a packaging addendum, not a thirteenth strategy-research round.',
                         'Clean materialization contains all 881 release entries plus generator/manifest; unrelated repository history and peer review files were not checked out.',
                         'No market data were deserialized, no 48-matrix recomputation, inference, refit, install, CI rerun or account writer was run.',
                         'Initial CI results were supplied by the parent and are not counted as this role executing those tests.',
                         'No real 2026 economic observation, V01/V02, other expert opinion or chair conclusion was read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False,indent=2))
