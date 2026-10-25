"""Round 07 synthetic pre-read API/path predicates. Never open forbidden data."""
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT=Path('/workspace/BTC-strategy')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')
sys.path.insert(0,str(ROOT/'src'))
from btc_strategy import artifacts,models,training

code_paths={name:ROOT/'src/btc_strategy'/name for name in ('artifacts.py','models.py','training.py')}
start_hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in code_paths.items()}
path_cases={
    '../repro-outside-placeholder':True,
    '/tmp/repro-outside-placeholder':True,
    'models/base_tree/2026/repro-placeholder.json.gz':True,
    'models/base_tree/fold2027/repro-placeholder.json.gz':True,
    'training_inputs/2026/base_tree.json.gz':True,
    'data/prices_2026.json':True,
    'artifacts/contexts/2026/repro-placeholder.json':True,
    'artifacts/V01-pretend/repro-placeholder.json':True,
    'artifacts/V02-pretend/repro-placeholder.json':True,
    'artifacts/V01/repro-placeholder.json':True,
    'artifacts/V02/repro-placeholder.json':True,
    'artifacts/v01-retained-validation/repro-placeholder.json':True,
    'provenance/folds/2026/repro-placeholder.json':True,
    'models/base_tree/2019/repro-placeholder.json.gz':False,
}
path_results=[]
for path,should_reject in path_cases.items():
    try:
        resolved=artifacts.resolve_artifact(path)
        rejected=False;message=None
    except ValueError as exc:
        rejected=True;message=str(exc)
    path_results.append({'synthetic_path':path,'required_reject':should_reject,'rejected_by_resolve_before_open':rejected,'message':message,'matches_contract':rejected==should_reject})

predicate_cases=[
    ('current_training_input','training_inputs/2019/base_tree.json.gz',True),
    ('wrong_year_training_input','training_inputs/2020/base_tree.json.gz',False),
    ('wrong_family_training_input','training_inputs/2019/short_median.json.gz',False),
    ('cached_replay_test_context','artifacts/contexts/high_return.json.gz',False),
    ('cached_factor_market','artifacts/factors/prices.json.gz',False),
    ('physical_test_input','data/walkforward-v1/2019/test.json',False),
    ('cached_targets','artifacts/targets/LP35.json.gz',False),
    ('provenance_current_test_receipt','provenance/studies/example/folds/2019/test-receipt.json',False),
    ('current_model','models/base_tree/2019/example.json.gz',True),
    ('wrong_year_model','models/base_tree/2020/example.json.gz',False),
    ('wrong_family_model','models/short_median/2019/example.json.gz',False),
    ('manifest','models/manifest.json',True),
    ('schema','models/feature_schema.json',True),
]
predicate_results=[]
for name,path,expected in predicate_cases:
    value=training.training_read_allowed(ROOT/path,'base_tree',2019)
    predicate_results.append({'name':name,'synthetic_path':path,'expected_allowed':expected,'actual_allowed':value,'pass':value==expected})
predicate_results.append({'name':'old_source_root','synthetic_path':'/workspace/BTCStrategyResearchLedger/data/repro-placeholder.json','expected_allowed':False,'actual_allowed':training.training_read_allowed('/workspace/BTCStrategyResearchLedger/data/repro-placeholder.json','base_tree',2019)})
outside_scope={'synthetic_path':'/tmp/repro-copied-test-context.json','allowed_by_training_predicate':training.training_read_allowed('/tmp/repro-copied-test-context.json','base_tree',2019),'qualification':'Predicate permits general outside-root library/filesystem reads except explicitly denied old projects; not a universal data capability sandbox.'}

class ReadAttempt(Exception):pass
class GuardInstallAttempt(Exception):pass
attempts=[]
def stop_read(*args,**kwargs):
    attempts.append({'operation':'read','args':[str(value) for value in args]})
    raise ReadAttempt('synthetic guard stopped before any file read')
def stop_guard(*args,**kwargs):
    attempts.append({'operation':'install_training_guard','args':[str(value) for value in args]})
    raise GuardInstallAttempt('unexpected guard install after invalid parameter')
originals=(models.read,models.read_verified,training.read,training.install_training_guard)
models.read=models.read_verified=training.read=stop_read
training.install_training_guard=stop_guard
market_future_end={'days':['2017-01-01','2026-01-01'],'prices':[100.,101.]}
market_future_middle={'days':['2017-01-01','2026-01-01','2025-12-31'],'prices':[100.,101.,100.]}
market_short_valid={'days':['2017-01-01','2017-01-02','2017-01-03'],'prices':[100.,101.,100.]}
api_cases=[
    ('annual_states_unknown_family',lambda:models.annual_states('unknown',2025)),
    ('annual_states_2026',lambda:models.annual_states('base_tree',2026)),
    ('annual_states_2017',lambda:models.annual_states('base_tree',2017)),
    ('annual_states_float_year',lambda:models.annual_states('base_tree',2025.0)),
    ('refit_unknown_family',lambda:training.refit('unknown',2025)),
    ('refit_2026',lambda:training.refit('base_tree',2026)),
    ('refit_2017',lambda:training.refit('base_tree',2017)),
    ('refit_float_year',lambda:training.refit('base_tree',2025.0)),
    ('reconstruct_unknown_family',lambda:models.reconstruct('unknown')),
    ('reconstruct_future_end_date',lambda:models.reconstruct('base_tree',market_future_end)),
    ('reconstruct_future_middle_date',lambda:models.reconstruct('base_tree',market_future_middle)),
    ('feature_matrix_unknown_family',lambda:models.feature_matrix('unknown',market_short_valid)),
    ('feature_matrix_future_middle_date',lambda:models.feature_matrix('base_tree',market_future_middle)),
]
api_results=[]
for name,call in api_cases:
    attempts.clear()
    try:
        value=call()
        outcome={'exception':None,'returned_shape':list(value.shape) if hasattr(value,'shape') else None}
    except Exception as exc:
        outcome={'exception':type(exc).__name__,'message':str(exc)}
    api_results.append({'case':name,**outcome,'attempts_before_rejection':list(attempts),'rejected_as_ValueError_before_read_or_guard':outcome['exception']=='ValueError' and not attempts})
models.read,models.read_verified,training.read,training.install_training_guard=originals

training_paths=[ROOT/'training_inputs'/str(year)/(family+'.json.gz') for year in range(2018,2026) for family in models.FAMILIES]
docs=list(ROOT.glob('*.md'))+(list((ROOT/'docs').rglob('*.md')) if (ROOT/'docs').exists() else [])
# Pure counterexample: a fixed 25% entry budget is not a maintained gross cap.
capital=Decimal('100');entry_notional=Decimal('25');price_ratio=Decimal('1.6')
current_short_notional=entry_notional*price_ratio
equity=capital-entry_notional*(price_ratio-1)
counterexample={'synthetic_only':True,'entry_budget_fraction':str(entry_notional/capital),'after_adverse_move_gross_fraction':str(current_short_notional/equity),'fees_and_financing_omitted_for_simple_demonstration':True}
end_hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in code_paths.items()}
result={'round':7,'code_hashes_at_start':start_hashes,'code_hashes_at_end':end_hashes,'code_snapshot_stable':start_hashes==end_hashes,
    'synthetic_path_predicates':path_results,'training_role_predicates':predicate_results,'outside_root_training_predicate_scope':outside_scope,
    'synthetic_public_api_pre_read_checks':api_results,'physical_training_file_expected_count':48,'physical_training_files_present_count':sum(path.is_file() for path in training_paths),
    'risk_document_paths_seen':[str(path.relative_to(ROOT)) for path in docs],
    'budget_not_gross_cap_pure_counterexample':counterexample,
    'real_forbidden_file_opened':False,'physical_training_input_contents_read':False,'training_guard_installed':False,
    'trained_or_replayed_account':False,'source_or_delivery_written':False,
    'r05_import_regression_repeated':False,'snapshot_limitation':'Current construction snapshot; no future forbidden data accessed and no final-release failure inferred.'}
with (OWN/'checks-r07.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(json.dumps({
    'code_snapshot_stable':result['code_snapshot_stable'],
    'path_contract_gaps':[row for row in path_results if not row['matches_contract']],
    'api_contract_gaps':[row for row in api_results if not row['rejected_as_ValueError_before_read_or_guard']],
    'training_predicates_all_match':all(row['actual_allowed']==row['expected_allowed'] for row in predicate_results),
    'training_files_present':result['physical_training_files_present_count'],'risk_docs':result['risk_document_paths_seen'],'budget_counterexample':counterexample},ensure_ascii=False,indent=2))
