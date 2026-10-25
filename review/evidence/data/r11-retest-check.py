"""Targeted closure check of the two original R11 synthetic boundary gaps."""
import ast
import copy
import gzip
import hashlib
import json
import re
import subprocess
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT=Path('/workspace/BTC-strategy')
OUTPUT=Path('/workspace/BTCExpertReview/workspaces/data/r11-retest-checks.json')
CANDIDATE='c7439216d55207a9a480153d7555f6709817e70a'


def extract(path,names,namespace):
    nodes=[node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


def read_plan(year,family):
    path=ROOT/f'training_inputs/{year}/{family}.json.gz'
    return json.loads(gzip.decompress(path.read_bytes()))


assert subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()==CANDIDATE
assert not subprocess.check_output(['git','-C',str(ROOT),'diff','--name-only','a642de16cea72875a99859e9108960b02636c584',CANDIDATE,'--','models','artifacts','training_inputs'],text=True).strip()
prior_paths=[Path('/workspace/BTCExpertReview/workspaces/data/r11.json'),Path('/workspace/BTCExpertReview/workspaces/data/r11-checks.json')]
prior_hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in prior_paths}
artifacts=extract(ROOT/'src/btc_strategy/artifacts.py',('resolve_artifact','read'),dict(Path=Path,ROOT=ROOT,re=re,json=json,gzip=gzip))
original_read_bytes=Path.read_bytes
attempted_opens=[]


def forbidden_open(path):
    attempted_opens.append(str(path))
    raise AssertionError('alias should be rejected before open')


alias_results=[]
Path.read_bytes=forbidden_open
try:
    for relative in ('artifacts/V01.json','artifacts/v02_unsafe.json'):
        try:
            artifacts['read'](relative)
        except ValueError as error:
            assert not attempted_opens
            alias_results.append(dict(path=relative,rejected_before_open=True,error=str(error)))
        else:
            raise AssertionError('original R11 alias remains allowed')
finally:
    Path.read_bytes=original_read_bytes


class StubFitReached(Exception):
    pass


class FitSentinel:
    def __init__(self,**kwargs):
        pass
    def fit(self,*arguments):
        counters['fit']+=1
        raise StubFitReached('fit sentinel only; no estimator fitted')


families=('base_tree','stop44','price47','short_huber','short_median','mining58')
training_file=ROOT/'src/btc_strategy/training.py'
tests=[]
for label,year,family in (
    ('duplicate_past_date',2019,'price47'),
    ('wrong_plan_family',2019,'price47'),
    ('future_date_interior',2019,'price47'),
    ('valid_price47_2019',2019,'price47'),
    ('valid_short_huber_2025',2025,'short_huber'),
    ('valid_missing_2018',2018,'price47'),
):
    plan=copy.deepcopy(read_plan(year,family))
    if label=='duplicate_past_date':plan['dates'][1]=plan['dates'][0]
    if label=='wrong_plan_family':plan['family']='short_huber'
    if label=='future_date_interior':plan['dates'][1]='2019-01-01'
    counters=dict(read=0,states=0,fit=0)
    def plan_reader(relative):
        counters['read']+=1
        assert relative==f'training_inputs/{year}/{family}.json.gz'
        return plan
    def states_reader(request_family,request_year):
        counters['states']+=1
        assert (request_family,request_year)==(family,year)
        if year==2018:return []
        if family.startswith('short_'):
            return [dict(n_features=44,family='SGB',seed=101,profile={},execution_lag=1,spec=dict(loss='huber',alpha=.9))]
        return [dict(n_features=47,family='EXTRA',seed=101,profile={})]
    namespace=dict(FAMILIES=families,install_training_guard=lambda *args:[],read=plan_reader,annual_states=states_reader,
                   np=np,date=date,timedelta=timedelta,ExtraTreesRegressor=FitSentinel,GradientBoostingRegressor=FitSentinel,
                   deepcopy=copy.deepcopy,threadpool_limits=lambda **kwargs:nullcontext())
    namespace=extract(training_file,('validate_training_plan','refit'),namespace)
    try:
        value=namespace['refit'](family,year)
        assert label=='valid_missing_2018'
        assert value['status']=='PRESERVED_MISSING' and counters==dict(read=1,states=1,fit=0)
        tests.append(dict(test=label,status='PRESERVED_MISSING',counters=dict(counters),actual_models_fitted=0))
    except ValueError as error:
        assert label in ('duplicate_past_date','wrong_plan_family','future_date_interior')
        assert counters==dict(read=1,states=0,fit=0)
        tests.append(dict(test=label,status='REJECT_BEFORE_STATES_AND_FIT',error=str(error),counters=dict(counters),actual_models_fitted=0))
    except StubFitReached:
        assert label in ('valid_price47_2019','valid_short_huber_2025')
        assert counters==dict(read=1,states=1,fit=1)
        tests.append(dict(test=label,status='VALID_PLAN_REACHES_FIT_SENTINEL',counters=dict(counters),actual_models_fitted=0))

predicate=extract(training_file,('training_read_allowed',),dict(Path=Path,ROOT=ROOT))['training_read_allowed']
outside_allowed=predicate('/tmp/data-r11-retest-fictional-outside.json','price47',2025)
assert outside_allowed
documentation=(ROOT/'docs/REPRODUCIBILITY.md').read_text()
assert 'hook为第三方库保留ROOT外读取，不能充当完整文件系统沙箱' in documentation
assert prior_hashes=={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in prior_paths}
result=dict(status='PASS_TARGETED',candidate_git=CANDIDATE,original_candidate='a642de16cea72875a99859e9108960b02636c584',
            aliases=alias_results,training_validation_order_tests=tests,raw_models_factors_and_training_inputs_unchanged=True,
            original_r11_artifact_hashes_preserved=prior_hashes,outside_root_predicate_still_allows=True,
            operating_system_sandbox_claim=False,root_external_boundary_documentation_still_present=True,
            original_two_gap_classes_closed_for_tested_examples=True,
            limitations=['Only the two original aliases, duplicate-date/wrong-family counterexamples, one future-date regression and three legal plan representatives were tested.',
                         'States, guards and fit were explicit stubs; no actual fitting, model loading or training guard installation occurred.',
                         'No full 48-prefix recomputation, offline inference or engine replay was repeated.',
                         'No real validation artifact, 2026 economic value, other expert opinion or chair artifact was opened.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False,indent=2))
