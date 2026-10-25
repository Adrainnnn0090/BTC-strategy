"""Round 05 public inference snapshot; only local reads, no writer/refit/account."""
import ast
import copy
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

DELIVERY=Path('/workspace/BTC-strategy')
SOURCE=Path('/workspace/BTCStrategyResearchLedger')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')
reads=set()
blocked_dependency_paths=[]
def audit(event,args):
    if event!='open' or not isinstance(args[0],(str,bytes)):
        return
    path=Path(os.fsdecode(args[0])).resolve()
    mode=args[1]
    is_write=mode is not None and any(flag in mode for flag in ('w','a','x','+'))
    if path.is_relative_to(DELIVERY):
        if is_write:
            raise AssertionError('review attempted delivery write')
        if any(part=='2026' or part.lower().startswith(('v01','v02')) for part in path.parts):
            raise AssertionError('forbidden economic path')
        reads.add(str(path.relative_to(DELIVERY)))
    if path.is_relative_to(SOURCE):
        raise AssertionError('inference must not read original source root')
    if 'binance_robot' in path.parts or path.is_relative_to('/workspace/BinanceTradingRobot/backend/src') or path.is_relative_to('/workspace/BinanceTradingRobot/research') or path.is_relative_to('/workspace/BinanceTradingRobot/strategy'):
        blocked_dependency_paths.append(str(path))
        raise AssertionError('inference must not load external trading project')
sys.addaudithook(audit)
sys.path.insert(0,str(DELIVERY/'src'))
independent_import_failure=None
instrument_shim_used=False
try:
    from btc_strategy import artifacts,models
except AssertionError as exc:
    independent_import_failure={'type':type(exc).__name__,'message':str(exc),'blocked_paths':list(blocked_dependency_paths)}
    # Continue numerical checks through an explicitly disclosed in-memory shim.
    # This does not repair delivery files or turn the clean import failure into PASS.
    import types
    from btc_strategy.instrument import INSTRUMENT,VENUE,paper_instrument
    package=types.ModuleType('binance_robot');package.__path__=[]
    execution=types.ModuleType('binance_robot.execution')
    execution.INSTRUMENT=INSTRUMENT;execution.VENUE=VENUE
    runner=types.ModuleType('binance_robot.runner');runner.paper_instrument=paper_instrument
    sys.modules.update({'binance_robot':package,'binance_robot.execution':execution,'binance_robot.runner':runner})
    instrument_shim_used=True
    from btc_strategy import artifacts,models

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

code_files=('models.py','strategies.py','artifacts.py')
start_hashes={name:digest(DELIVERY/'src/btc_strategy'/name) for name in code_files}
manifest=artifacts.read('models/manifest.json')
schema=artifacts.read('models/feature_schema.json')
expected_seeds=[101,307,509,701,907,1103,1701]
rosters=[]
for family in models.FAMILIES:
    for year in range(2018,2026):
        route=next(row for row in manifest if row['family']==family and row['fold_year']==year)
        states=models.annual_states(family,year)
        groups={lag:[state['seed'] for state in states if state.get('execution_lag',0)==lag] for lag in ((1,2) if family.startswith('short_') else (0,))}
        valid=not states if year==2018 else all(seeds==expected_seeds for seeds in groups.values())
        rosters.append({'family':family,'year':year,'state_count':len(states),'seed_groups':groups,'roster_exact':valid,
            'schema_width_exact':route['feature_width']==len(schema[route['feature_schema']]),
            'schema_indices_exact':[item['index'] for item in schema[route['feature_schema']]]==list(range(route['feature_width'])),
            'files_digest_exact':all(digest(DELIVERY/item['path'])==item['sha256'] for item in route['files'])})

verification=[]
for family in models.FAMILIES:
    result=models.verify_family(family)
    verification.append(result)
    print(json.dumps({'actual_reconstruction':result}),flush=True)

market=artifacts.read('artifacts/factors/market.json.gz')
price_only_error=None
try:
    models.reconstruct('price47',{'days':market['days'],'prices':market['prices']})
except Exception as exc:
    price_only_error={'type':type(exc).__name__,'message':str(exc)}

# Only in-memory substitutes; on-disk manifest/model bytes are untouched.
original_read=models.read
fault_results={}
for fault in ('duplicate_seed_roster','missing_second_head','drifted_model_initial','unavailable_2019'):
    injected=copy.deepcopy(manifest)
    family='short_median' if fault=='missing_second_head' else 'base_tree'
    row=next(item for item in injected if item['family']==family and item['fold_year']==2019)
    if fault=='duplicate_seed_roster':
        row['files'].append(copy.deepcopy(row['files'][0]))
    elif fault=='missing_second_head':
        row['files']=[item for item in row['files'] if '/MEDIAN_L1-' in item['path']]
    elif fault=='unavailable_2019':
        row['missing']=True;row['files']=[]
    target=row['files'][0]['path'] if row['files'] else None
    def fake_read(path):
        if path=='models/manifest.json':
            return injected
        value=original_read(path)
        if fault=='drifted_model_initial' and path==target:
            value=copy.deepcopy(value)
            value['state']['initial']+=1.
        return value
    models.read=fake_read
    try:
        states=models.annual_states(family,2019)
        fault_results[fault]={'rejected':False,'returned_state_count':len(states),'returned_head_lags':sorted(set(state.get('execution_lag',0) for state in states))}
    except Exception as exc:
        fault_results[fault]={'rejected':True,'exception':type(exc).__name__,'message':str(exc)}
    finally:
        models.read=original_read

absolute_strings=[]
for name in code_files:
    tree=ast.parse((DELIVERY/'src/btc_strategy'/name).read_bytes())
    absolute_strings.extend({'file':name,'line':node.lineno,'literal':node.value} for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith('/workspace'))
end_hashes={name:digest(DELIVERY/'src/btc_strategy'/name) for name in code_files}
result={'round':5,'code_hashes_at_start':start_hashes,'code_hashes_at_end':end_hashes,'code_snapshot_stable':start_hashes==end_hashes,
    'clean_independent_import_passed':independent_import_failure is None,'clean_independent_import_failure':independent_import_failure,
    'in_memory_local_instrument_shim_used_for_continued_checks':instrument_shim_used,
    'roster_schema_digest_checks':rosters,'all_roster_schema_digest_checks_pass':all(all(row[key] for key in ('roster_exact','schema_width_exact','schema_indices_exact','files_digest_exact')) for row in rosters),
    'six_family_actual_reconstructions':verification,'all_actual_reconstructions_pass':len(verification)==6 and all(item['max_error']<=item['tolerance'] and item['availability_exact'] for item in verification),
    'price_only_market_call_error':price_only_error,'in_memory_fault_outcomes':fault_results,
    'active_interface_absolute_workspace_literals':absolute_strings,
    'delivery_read_paths':sorted(reads),'training_material_read':any(path.startswith('training_inputs/') for path in reads),
    'old_source_and_external_trading_project_reads_blocked':True,'binance_robot_modules_loaded':[name for name in sys.modules if name=='binance_robot' or name.startswith('binance_robot.')],
    'forbidden_data_read':False,'on_disk_faults_written':False,'training_or_writer_or_account_executed':False,
    'snapshot_limitation':'trainer and global hash gate still under development; this is an interface snapshot, not final failure or final acceptance'}
with (OWN/'checks-r05.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(json.dumps({key:result[key] for key in ('clean_independent_import_passed','clean_independent_import_failure','in_memory_local_instrument_shim_used_for_continued_checks','code_snapshot_stable','all_roster_schema_digest_checks_pass','all_actual_reconstructions_pass','price_only_market_call_error','in_memory_fault_outcomes','active_interface_absolute_workspace_literals','training_material_read','binance_robot_modules_loaded')},ensure_ascii=False,indent=2))
