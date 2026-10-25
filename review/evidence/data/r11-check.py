"""Bounded R11 documentation and synthetic entry-boundary regression; no fits."""
import ast
import copy
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT=Path('/workspace/BTC-strategy')
OUTPUT=Path('/workspace/BTCExpertReview/workspaces/data/r11-checks.json')
OLD='1b008bfd4a9d1af9a73ff830fb7f8a1b72425fbf'
NEW='a642de16cea72875a99859e9108960b02636c584'


def git(*arguments):
    return subprocess.check_output(['git','-C',str(ROOT),*arguments],text=True)


def read(path):
    assert not any(part in path.parts for part in ('review','verification','2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)


def functions(path,names,namespace):
    tree=ast.parse(path.read_text())
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected}==set(names)
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


assert git('rev-parse','HEAD').strip()==NEW
unchanged_paths=['artifacts','models','training_inputs','src/btc_strategy/_runtime','src/btc_strategy/_frozen',
                 'src/btc_strategy/models.py','src/btc_strategy/artifacts.py','src/btc_strategy/training.py',
                 'src/btc_strategy/validation.py','src/btc_strategy/execution.py']
assert not git('diff','--name-only',OLD,NEW,'--',*unchanged_paths).strip()
assert not git('diff','--name-only',NEW,'--',*unchanged_paths,'src/btc_strategy/replay.py').strip()
old_release=json.loads(git('show',OLD+':provenance/release_manifest.json'))
new_release=read(ROOT/'provenance/release_manifest.json')
old_records={item['path']:item for item in old_release['files']}
new_records={item['path']:item for item in new_release['files']}
assert set(old_records)==set(new_records) and len(new_records)==886
changed=[path for path in new_records if old_records[path]!=new_records[path]]
assert changed==['src/btc_strategy/replay.py']
replay_path=ROOT/changed[0]
assert hashlib.sha256(replay_path.read_bytes()).hexdigest()==new_records[changed[0]]['sha256']
assert replay_path.stat().st_size==new_records[changed[0]]['bytes']
assert sum(item['bytes'] for item in new_records.values())==56445495
old_run=next(node for node in ast.parse(git('show',OLD+':src/btc_strategy/replay.py')).body if isinstance(node,ast.FunctionDef) and node.name=='run')
new_run=copy.deepcopy(next(node for node in ast.parse(replay_path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='run'))
new_run.body=[node for node in new_run.body if not (isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='scopes' for target in node.targets))]
for node in new_run.body:
    if isinstance(node,ast.Return):
        node.value.keywords=[keyword for keyword in node.value.keywords if keyword.arg not in ('metric_scope','risk_qualification')]
assert ast.dump(old_run,include_attributes=False)==ast.dump(new_run,include_attributes=False)
documentation=(ROOT/'docs/REPRODUCIBILITY.md').read_text()
documentation_line=next((i,line) for i,line in enumerate(documentation.splitlines(),1) if 'hook为第三方库保留ROOT外读取' in line)
assert all(fragment in documentation_line[1] for fragment in ('正常训练CLI只显式请求当前plan与模型','不能充当完整文件系统沙箱','容器/OS挂载边界'))

artifact_ns=functions(ROOT/'src/btc_strategy/artifacts.py',('resolve_artifact','read','read_verified'),
                      dict(Path=Path,ROOT=ROOT,re=re,json=json,gzip=gzip,hashlib=hashlib))
malformed_paths=['../BTCStrategyResearchLedger/data/x.json','/workspace/BTCStrategyResearchLedger/data/x.json',
                 'provenance/studies/B10/registration.json','review/rounds/01/chair.json',
                 'models/base_tree/2026/model.json.gz','training_inputs/2027/price47.json.gz',
                 'artifacts/economic-2028.json','artifacts/V01/rows.json','artifacts/v02-unsafe/rows.json']
original_read_bytes=Path.read_bytes
attempts=[]


def bomb_open(path):
    attempts.append(str(path))
    raise AssertionError('data must be rejected before opening')


Path.read_bytes=bomb_open
path_tests=[]
try:
    for relative in malformed_paths:
        before=len(attempts)
        try:
            artifact_ns['read'](relative)
        except ValueError as error:
            assert len(attempts)==before
            path_tests.append(dict(path=relative,rejected_before_open=True,error=str(error)))
        else:
            raise AssertionError('expected path rejection')
finally:
    Path.read_bytes=original_read_bytes
aliases=[]
for relative in ('artifacts/V01.json','artifacts/v02_unsafe.json'):
    resolved=artifact_ns['resolve_artifact'](relative)
    assert resolved.is_relative_to(ROOT)
    aliases.append(dict(path=relative,pure_path_predicate_allows=True,file_opened=False,
                        interpretation='Naming-pattern coverage only; no real validation artifact exists or is read in this probe.'))

temporary=Path(tempfile.mkdtemp(prefix='btc-data-r11-path-'))
(temporary/'models').mkdir()
(temporary/'models/alias').symlink_to('/tmp/data-r11-nonexistent-outside')
symbolic_ns=functions(ROOT/'src/btc_strategy/artifacts.py',('resolve_artifact',),dict(Path=Path,ROOT=temporary,re=re))
try:
    symbolic_ns['resolve_artifact']('models/alias/data.json')
except ValueError:
    symlink_escape_rejected=True
else:
    raise AssertionError('symlink escape accepted')
(temporary/'models/alias').unlink();(temporary/'models').rmdir();temporary.rmdir()

hash_reads=[]
Path.read_bytes=lambda path:(hash_reads.append(str(path)) or b'{"synthetic":true}')
artifact_ns['json']=SimpleNamespace(loads=lambda value:(_ for _ in ()).throw(AssertionError('hash must fail before parsing')))
try:
    try:
        artifact_ns['read_verified']('models/price47/2025/synthetic.json','0'*64)
    except ValueError as error:
        assert 'hash mismatch' in str(error) and len(hash_reads)==1
    else:
        raise AssertionError('bad hash accepted')
finally:
    Path.read_bytes=original_read_bytes
    artifact_ns['json']=json

families=('base_tree','stop44','price47','short_huber','short_median','mining58')
manifest_reads=[];verified_reads=[]
synthetic_manifest=[];synthetic_packet={}


def fake_manifest(path):
    manifest_reads.append(path)
    return synthetic_manifest


def fake_verified(path,digest):
    verified_reads.append(path)
    return synthetic_packet


annual_ns=functions(ROOT/'src/btc_strategy/models.py',('annual_states',),dict(FAMILIES=families,read=fake_manifest,read_verified=fake_verified))
annual_tests=[]
for family,year in (('not_a_family',2025),('price47',2026),('price47',2017),('price47',True),('price47',2025.0),('price47','2025')):
    manifest_reads.clear();verified_reads.clear()
    try:
        annual_ns['annual_states'](family,year)
    except ValueError:
        assert not manifest_reads and not verified_reads
        annual_tests.append(dict(family=family,year=year,rejected_before_manifest=True))
    else:
        raise AssertionError('invalid family/year accepted')
seeds=[101,307,509,701,907,1103,1701]
base_entry=dict(family='price47',fold_year=2025,missing=False,feature_width=47,
                files=[dict(path='models/price47/2025/synthetic.json',sha256='synthetic')])
base_packet=dict(cutoff='2024-12-31',members=[dict(seed=seed,n_features=47) for seed in seeds])
for label in ('valid_roster','wrong_file_year','wrong_file_family','wrong_packet_cutoff','wrong_width','duplicate_seed'):
    synthetic_manifest[:]=[copy.deepcopy(base_entry)];synthetic_packet.clear();synthetic_packet.update(copy.deepcopy(base_packet))
    if label=='wrong_file_year':synthetic_manifest[0]['files'][0]['path']='models/price47/2024/synthetic.json'
    if label=='wrong_file_family':synthetic_manifest[0]['files'][0]['path']='models/stop44/2025/synthetic.json'
    if label=='wrong_packet_cutoff':synthetic_packet['cutoff']='2025-12-31'
    if label=='wrong_width':synthetic_packet['members'][0]['n_features']=44
    if label=='duplicate_seed':synthetic_packet['members'][0]['seed']=307
    manifest_reads.clear();verified_reads.clear()
    try:
        value=annual_ns['annual_states']('price47',2025)
        assert label=='valid_roster' and len(value)==7
        annual_tests.append(dict(test=label,status='ACCEPT_VALID_SYNTHETIC'))
    except ValueError as error:
        assert label!='valid_roster'
        if label in ('wrong_file_year','wrong_file_family'):assert not verified_reads
        annual_tests.append(dict(test=label,status='REJECT',error=str(error)))

development_market=functions(ROOT/'src/btc_strategy/validation.py',('development_market',),dict(date=date,timedelta=timedelta,math=__import__('math')))['development_market']
feature_calls=[]


def feature_bomb(*arguments):
    feature_calls.append(True)
    raise AssertionError('bad dates must fail before feature calculation')


feature_ns=functions(ROOT/'src/btc_strategy/models.py',('feature_matrix',),dict(FAMILIES=families,development_market=development_market,matrix=feature_bomb,append_volume=feature_bomb,ablate=feature_bomb))
date_tests=[]
for family in ('base_tree','price47','mining58'):
    for label,bad_dates in [('future',['2017-01-01','2026-01-01']),('duplicate',['2017-01-01','2017-01-01']),('gap',['2017-01-01','2017-01-03'])]:
        try:
            feature_ns['feature_matrix'](family,dict(days=bad_dates,prices=[1.,1.]))
        except ValueError:
            assert not feature_calls
            date_tests.append(dict(family=family,test=label,rejected_before_features=True))
        else:
            raise AssertionError('bad economic clock accepted')

sample_plans=[]
for year,family in ((2018,'price47'),(2019,'price47'),(2025,'price47'),(2025,'short_huber'),(2025,'mining58')):
    relative=f'training_inputs/{year}/{family}.json.gz';path=ROOT/relative;plan=read(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==new_records[relative]['sha256']
    count=(date(year-1,12,31)-date(2017,1,1)).days+1
    assert plan['family']==family and plan['fold_year']==year and plan['cutoff']==f'{year-1}-12-31'
    assert plan['dates']==[(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(count)]
    assert len(plan['features'])==count and plan['cut_index']==count-1
    if plan['model_missing']:assert year==2018 and not plan['ids'] and not plan['targets']
    else:assert plan['ids']==sorted(set(plan['ids'])) and plan['ids'][-1]+(62 if family.startswith('short_') else 61)<=plan['cut_index']-6
    sample_plans.append(dict(family=family,year=year,physical_rows=count,source_hash_matched=True,physical_prefix_exact=True))

class StubFitReached(Exception):
    pass


class FitBomb:
    def __init__(self,**kwargs):
        pass
    def fit(self,*arguments):
        raise StubFitReached('No model fitted: sentinel reached')


original=read(ROOT/'training_inputs/2019/price47.json.gz')
plan_tests=[]
for label in ('valid_baseline','future_date_interior','wrong_fold_year','wrong_cutoff','immature_ids','duplicate_past_date','wrong_plan_family'):
    plan=copy.deepcopy(original)
    if label=='future_date_interior':plan['dates'][1]='2019-01-01'
    if label=='wrong_fold_year':plan['fold_year']=2020
    if label=='wrong_cutoff':plan['cutoff']='2019-12-31'
    if label=='immature_ids':plan['ids'][-1]=plan['cut_index']-60
    if label=='duplicate_past_date':plan['dates'][1]=plan['dates'][0]
    if label=='wrong_plan_family':plan['family']='short_huber'
    namespace=dict(FAMILIES=families,install_training_guard=lambda *args:[],read=lambda *args:plan,
                   annual_states=lambda *args:[dict(n_features=47,family='EXTRA',seed=101,profile={})],
                   np=np,date=date,ExtraTreesRegressor=FitBomb,deepcopy=copy.deepcopy,
                   threadpool_limits=lambda **kwargs:nullcontext())
    refit=functions(ROOT/'src/btc_strategy/training.py',('refit',),namespace)['refit']
    try:
        refit('price47',2019)
    except AssertionError:
        assert label in ('future_date_interior','wrong_fold_year','wrong_cutoff','immature_ids')
        plan_tests.append(dict(test=label,status='REJECT_BEFORE_STUB_FIT'))
    except StubFitReached:
        assert label in ('valid_baseline','duplicate_past_date','wrong_plan_family')
        plan_tests.append(dict(test=label,status='REACHES_STUB_FIT',model_actually_fitted=False))
    else:
        raise AssertionError('unexpected synthetic refit completion')
training_predicate=functions(ROOT/'src/btc_strategy/training.py',('training_read_allowed',),dict(Path=Path,ROOT=ROOT))['training_read_allowed']
assert training_predicate('/tmp/data-r11-fictional-outside.json','price47',2025)
assert not training_predicate(ROOT/'artifacts/factors/prices.json.gz','price47',2025)
assert not training_predicate(ROOT/'training_inputs/2025/stop44.json.gz','price47',2025)

result=dict(status='PASS_BOUNDED_WITH_RESIDUALS',candidate_git=NEW,
            old_candidate=OLD,unchanged_economic_data_model_and_guard_paths=unchanged_paths,
            release=dict(files=886,declared_bytes=56445495,unchanged_manifest_entries=885,changed_manifest_path=changed[0],changed_file_actual_size_hash_matched=True),
            replay_economic_statements_unchanged_after_metadata_normalization=True,
            documentation=dict(path='docs/REPRODUCIBILITY.md',line=documentation_line[0],text=documentation_line[1],matches_root_external_read_policy=True),
            malformed_path_rejections=path_tests,symlink_escape_rejected_before_open=symlink_escape_rejected,
            model_hash_mismatch_rejected_before_json_parse=True,annual_model_tests=annual_tests,date_tests=date_tests,
            actual_sample_training_prefixes=sample_plans,synthetic_plan_tests=plan_tests,
            residuals=dict(validation_alias_path_predicates=aliases,
                           malformed_past_date_and_family_metadata_may_reach_fit_stub=True,
                           outside_root_training_reads_still_allowed_and_now_documented=True,
                           current_export_prefix_or_model_data_violation=False),
            harness_note='An exploratory extraction initially omitted the threadpool_limits stub and raised NameError; only the role-local harness was completed with nullcontext, then the recorded synthetic tests were run. No source change or model fitting occurred.',
            limitations=['The byte comparison of unchanged core uses Git tree equality and prior R10 full verification; unchanged 885 files were not rehashed again in this round.',
                         'Only five actual training plans were sampled; all 48 feature matrices and offline forecasts were not recomputed.',
                         'Synthetic refit tests replace fit and loading guards with explicit stubs to test validation ordering only; they never fit an estimator or install a new global guard.',
                         'Allowed aliases and external paths were resolved/predicate-tested only; no true V01/V02 or 2026 economic value was opened.',
                         'No other expert, chair, review or verification conclusions were read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('annual_model_tests','date_tests','malformed_path_rejections','documentation')},ensure_ascii=False,indent=2))
