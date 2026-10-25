"""B-only registration inventory checks; no legacy aggregate result tables are opened."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SOURCE=Path('/workspace/BTCStrategyResearchLedger')
NEW=Path('/workspace/BTC-strategy')
OUTPUT=Path('/workspace/BTCExpertReview/workspaces/data/r08-checks.json')


def read(path):
    assert not any(part in path.parts for part in ('2026','review','verification','V01-2026-retained-validation','V02-buy-and-hold-validation'))
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


registry=read(NEW/'research/trial_registry.json')
rows=registry['rows']
assert registry['cohorts']==len(rows)==115
assert len({row['study'] for row in rows})==len(rows)
expected_paths={str(path.relative_to(SOURCE)) for path in (SOURCE/'studies').glob('B*/registration.json')}
assert {row['source'] for row in rows}==expected_paths
registrations={}
by_id=defaultdict(list)
by_descriptor=defaultdict(list)
metadata_recipe_entries=0
fit_details_unrepresented=[]
fit_keys=('model_fits','new_model_fits','research_member_fits','final_members','new_final_members_cap',
          'pipeline_estimator_fits','independent_inner_library_fits','new_rank_fits','new_member_fits_cap')
for row in rows:
    assert row['study'].startswith('B')
    assert row['source']==f'studies/{row["study"]}/registration.json'
    path=SOURCE/row['source']
    assert row['registration_sha256']==sha(path)
    registration=read(path)
    registrations[row['study']]=registration
    recipes=registration.get('recipes',[])
    assert row['recipe_count']==len(recipes)
    assert row['recipe_ids']==[recipe['id'] for recipe in recipes]
    assert len(set(row['recipe_ids']))==len(row['recipe_ids'])
    metadata_recipe_entries+=len(recipes)
    for recipe in recipes:
        descriptor=json.dumps(recipe,sort_keys=True,separators=(',',':'))
        address=dict(study=row['study'],recipe_id=recipe['id'])
        by_id[recipe['id']].append(dict(**address,recipe=recipe))
        by_descriptor[descriptor].append(address)
    declared={key:registration[key] for key in fit_keys if key in registration}
    if row['reported_new_fits'] is None and declared:
        fit_details_unrepresented.append(dict(study=row['study'],registry_reported_new_fits=None,source_fields=declared))

collisions={identifier:items for identifier,items in by_id.items() if len({item['study'] for item in items})>1}
descriptor_variants={identifier:items for identifier,items in collisions.items()
                     if len({json.dumps(item['recipe'],sort_keys=True) for item in items})>1}
identical_descriptors=[dict(recipe=json.loads(descriptor),addresses=addresses)
                       for descriptor,addresses in by_descriptor.items() if len(addresses)>1]
c04_examples=[item for item in by_id['C04'] if item['study'] in ('B31-constant-sizing-controls','B85-price-core-consensus-entry')]
assert len(c04_examples)==2
assert next(item['recipe'] for item in c04_examples if item['study'].startswith('B31'))['mode']=='CONSTANT'
assert next(item['recipe'] for item in c04_examples if item['study'].startswith('B85'))['gate']=='BOTH2'

# Prove inherited economic-book identity with actual file digests, not ID spelling.
b109=registrations['B109-long-profit-local-coordinate']
legacy=[recipe for recipe in b109['recipes'] if recipe['kind']=='LEGACY']
new_arms=[recipe for recipe in b109['recipes'] if recipe['kind']=='LONG_PROFIT']
assert len(legacy)==12 and len(new_arms)==4
control_pairs=[]
for recipe in legacy:
    identifier=recipe['id']
    for case in ('BASE','STRESS','SEVERE','DELAY'):
        candidates=[relative for relative in b109['source'] if relative.endswith(f'/accounts/{identifier}/{case}.json.gz')]
        assert len(candidates)==1,(identifier,case,candidates)
        relative=candidates[0]
        original=SOURCE/relative
        descendant=SOURCE/f'studies/B109-long-profit-local-coordinate/accounts/{identifier}/{case}.json.gz'
        assert sha(original)==b109['source'][relative]==sha(descendant)
        control_pairs.append(dict(descendant=str(descendant.relative_to(SOURCE)),source=relative,sha256=sha(original)))
assert len(control_pairs)==b109['exact_controls']==48

# Small scoped search evidence: trace counts are not model-fit counts or global effective N.
search_examples=[]
for year in (2021,2025):
    folder=SOURCE/f'studies/B29-prior-forecast-exits/folds/{year}'
    training,seal=read(folder/'training.json'),read(folder/'seal.json')
    assert seal['training_sha256']==sha(folder/'training.json')
    assert training['cutoff']==seal['cutoff']==f'{year-1}-12-31'
    configs=0
    for parent,choice in training['choices'].items():
        order=choice['evaluation_order']
        assert len(order)==len(set(order))==choice['evaluation_count']
        assert set(order)==set(choice['evaluated'])==set(choice['candidate_sha256'])
        configs+=len(order)
        for identifier in order:
            path=folder/'calibration'/parent/identifier/'candidate.json'
            assert sha(path)==choice['candidate_sha256'][identifier]
    assert configs==training['counts']['configs']
    assert training['counts']['attempts']==4*configs
    search_examples.append(dict(study='B29-prior-forecast-exits',fold_year=year,
                                model_fits=training['model_fits'],scoped_configurations=configs,
                                scoped_account_attempts=training['counts']['attempts'],
                                unique_evaluation_order_and_candidate_hashes=True))

additional_contracts=sorted(str(path.relative_to(SOURCE)) for path in (SOURCE/'studies').glob('B*/*registration.json') if path.name!='registration.json')
result=dict(status='PASS',registry_source_hashes_matched=115,registry_standard_B_registrations_complete=True,
            metadata_recipe_entries=metadata_recipe_entries,
            metadata_recipe_entries_qualification='Syntactic rows only: inherited controls, repeated configurations, source audits and heterogeneous searches are not independent trials.',
            cross_study_reused_recipe_ids=len(collisions),
            reused_ids_with_different_metadata_descriptors=len(descriptor_variants),
            identical_metadata_descriptor_groups=len(identical_descriptors),
            c04_namespace_collision_examples=c04_examples,
            inherited_controls=dict(study='B109-long-profit-local-coordinate',recipe_rows=16,new_long_profit_coordinates=4,
                                    inherited_recipe_controls=12,exact_inherited_books=48,pairs=control_pairs),
            fit_fields_unrepresented_when_registry_null=fit_details_unrepresented,
            zero_recipe_search_example=dict(study='B01-price-mechanisms',recipe_count=0,
                                            candidate_cap=registrations['B01-price-mechanisms']['candidate_cap'],
                                            account_cap=registrations['B01-price-mechanisms']['account_cap'],
                                            note='Caps, not actual completed attempts; absence of recipes does not mean zero search.'),
            scoped_selection_trace_examples=search_examples,
            additional_registration_contract_metadata_outside_standard_inventory=additional_contracts,
            effective_independent_test_count=None,
            correction_sufficiency='Registry provides source-bound registration inventory, not a complete candidate-outcome/dependence/selection history for multiple-testing correction.',
            limitations=['Exact descriptor repetition is metadata repetition; semantic/economic deduplication requires source lineage or complete path equality.',
                         'The 48 B109 inherited books are exact repeats of bound prior books, not 48 independent market samples.',
                         'The two B29 examples describe only those training folds; their counts are not summed into a global test count.',
                         'Additional source/preparation contracts are metadata coverage gaps, not automatically extra economic trials.',
                         'No legacy aggregate result table, V01/V02, 2026 economic record, expert opinion or chair artifact was read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('inherited_controls','fit_fields_unrepresented_when_registry_null','additional_registration_contract_metadata_outside_standard_inventory')},ensure_ascii=False,indent=2))
