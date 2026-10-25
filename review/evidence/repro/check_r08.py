"""Round 08 registration lineage, failure retention and shared model wiring only."""
import ast
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path

SOURCE=Path('/workspace/BTCStrategyResearchLedger')
ROOT=Path('/workspace/BTC-strategy')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')

def raw(path):
    path=Path(path)
    if any(token in str(path).lower() for token in ('2026','v01','v02')):
        raise ValueError('forbidden path')
    return path.read_bytes()

def sha(path):return hashlib.sha256(raw(path)).hexdigest()
def read(path):return json.loads(raw(path))
def canonical_sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

registry=read(ROOT/'research/trial_registry.json')
registry_checks=[]
recipe_groups=defaultdict(list)
recipe_ids=Counter()
source_registrations={str(path.relative_to(SOURCE)) for path in (SOURCE/'studies').glob('B*/registration.json')}
local_registration_copy_count=0
for row in registry['rows']:
    source=row['source']
    assert source.startswith('studies/B') and source.endswith('/registration.json')
    original=read(SOURCE/source)
    recipes=original.get('recipes',[])
    registry_checks.append({'study':row['study'],'source':source,'sha256_exact':sha(SOURCE/source)==row['registration_sha256'],
        'recipe_count_exact':len(recipes)==row['recipe_count'],
        'recipe_ids_exact':[item['id'] for item in recipes]==row['recipe_ids']})
    if recipes:
        recipe_groups[canonical_sha(recipes)].append(row['study'])
    recipe_ids.update(row['recipe_ids'])
    local=ROOT/'provenance'/source
    if local.exists():
        assert sha(local)==row['registration_sha256']
        local_registration_copy_count+=1

selected_retention_paths=[
    'studies/B31-constant-sizing-controls/original-verifier-failure.txt',
    'studies/B31-constant-sizing-controls/original-report-failure.txt',
    'studies/B31-constant-sizing-controls/verifier-correction.md',
    'studies/B60-trend-alpha-controls/run-failed.log',
    'studies/B60-trend-alpha-controls/verification-failed.log',
    'studies/B64-retained-same-window-comparison/failure.md',
    'studies/B64-retained-same-window-comparison/verification-failed.log',
    'studies/B88-short-net-loss-families/original-failure.log',
    'studies/B100-persistent-negative-long-exits/original-run-failure.json',
    'studies/B103-faster-cold-short-trend/original-verification-failure.json',
    'studies/B103A-cold-source-mask-independent-audit/analysis-metadata-correction.json',
    'studies/B105-cold-entry-momentum/analysis-kind-correction.json',
    'studies/B107-cold-short-profit-trailing/decision-metadata-correction.json',
    'studies/B109-long-profit-local-coordinate/spec-metadata-correction.json',
]
retention=[]
for source in selected_retention_paths:
    original=SOURCE/source;local=ROOT/'provenance'/source
    retention.append({'source':source,'source_exists':original.is_file(),'source_sha256':sha(original),
        'expected_delivery':str(local.relative_to(ROOT)),'delivery_exists':local.is_file(),
        'delivery_sha256_exact':sha(local)==sha(original) if local.is_file() else None})

technical_failure_registration_comparison=[]
for prefix in ('B88-short-net-loss-families','B88A-short-net-loss-families'):
    row=next(item for item in registry['rows'] if item['study']==prefix)
    model_files=[path for year in range(2018,2026) for path in (SOURCE/'studies'/prefix/'folds'/str(year)/'models').glob('*.json.gz')]
    technical_failure_registration_comparison.append({'study':prefix,'registered_reported_new_fits':row['reported_new_fits'],'actual_historical_model_file_count':len(model_files),'has_original_failure_log':(SOURCE/'studies'/prefix/'original-failure.log').exists()})

model_manifest=read(ROOT/'models/manifest.json')
all_model_files=[item for row in model_manifest for item in row['files']]
model_files_digest_check=all(sha(ROOT/item['path'])==item['sha256'] for item in all_model_files)

# Extract only the strategy wiring function and replace all data operations by
# synthetic callbacks. No model, context, account, training or source loader runs.
tree=ast.parse(raw(ROOT/'src/btc_strategy/models.py'))
wiring=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='rebuild_context')
calls=[]
def context(name):return [{'scores':{}},{'scores':{}},{'scores':{}},{}]
def rebuilt(family):calls.append(family);return ('synthetic-placeholder',)
namespace={'context':context,'_rebuilt':rebuilt}
exec(compile(ast.fix_missing_locations(ast.Module(body=[wiring],type_ignores=[])),'<synthetic-model-wiring>','exec'),namespace)
strategies=('LP35','TS04','ME01','MX03','B88A_S03','K02','Y01','C02','C04')
strategy_families={}
for strategy in strategies:
    calls.clear();namespace['rebuild_context'](strategy)
    strategy_families[strategy]=sorted(set(calls))
family_set_groups=defaultdict(list)
for strategy,families in strategy_families.items():family_set_groups[tuple(families)].append(strategy)

result={'round':8,'registry_scope':registry['scope'],'registry_interpretation':registry['interpretation'],
    'cohorts_declared':registry['cohorts'],'registry_row_count':len(registry['rows']),
    'all_registration_checks_pass':all(all(row[key] for key in ('sha256_exact','recipe_count_exact','recipe_ids_exact')) for row in registry_checks),
    'registry_source_path_roster_exact_to_B_registrations':{row['source'] for row in registry['rows']}==source_registrations,
    'source_B_registration_count':len(source_registrations),'registration_checks':registry_checks,
    'raw_registration_copies_present_in_delivery':local_registration_copy_count,
    'recipe_entry_count_not_independent_tests':sum(row['recipe_count'] for row in registry['rows']),
    'same_full_recipe_array_groups':[{'recipe_array_sha256':key,'studies':members} for key,members in recipe_groups.items() if len(members)>1],
    'most_repeated_recipe_names_not_independent_trials':recipe_ids.most_common(12),
    'selected_failure_correction_retention':retention,
    'selected_retention_source_file_count':len(retention),'selected_retention_exact_copy_count':sum(row['delivery_sha256_exact'] is True for row in retention),
    'technical_failure_registered_vs_actual_model_files':technical_failure_registration_comparison,
    'physical_model_file_count':len(all_model_files),'unique_model_file_digest_count':len({item['sha256'] for item in all_model_files}),
    'all_current_model_file_digests_match':model_files_digest_check,
    'strategy_numeric_family_wiring':strategy_families,
    'same_numeric_family_set_groups':[{'families':list(key),'strategies':members} for key,members in family_set_groups.items() if len(members)>1],
    'independent_market_sample_or_effective_trial_count_estimated':False,
    'boundary_repairs_regression_executed':False,'trained_replayed_account_or_searched_strategy':False,'source_or_delivery_written':False,
    'scope_limitation':'B registration metadata and selected known failure/correction files only; no V/2026 economic data or other expert review files.'}
with (OWN/'checks-r08.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(json.dumps({key:result[key] for key in ('cohorts_declared','registry_row_count','all_registration_checks_pass','registry_source_path_roster_exact_to_B_registrations','source_B_registration_count','raw_registration_copies_present_in_delivery','recipe_entry_count_not_independent_tests','same_full_recipe_array_groups','most_repeated_recipe_names_not_independent_trials','selected_retention_source_file_count','selected_retention_exact_copy_count','technical_failure_registered_vs_actual_model_files','physical_model_file_count','unique_model_file_digest_count','all_current_model_file_digests_match','strategy_numeric_family_wiring','same_numeric_family_set_groups')},ensure_ascii=False,indent=2))
