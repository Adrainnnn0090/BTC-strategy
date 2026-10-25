"""Round 03 label/state contracts; read-only, never fit or import research code."""
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

SOURCE = Path('/workspace/BTCStrategyResearchLedger')
DELIVERY = Path('/workspace/BTC-strategy')
OWN = Path('/workspace/BTCExpertReview/workspaces/repro')

def raw(path):
    path=Path(path)
    if any(token in str(path).lower() for token in ('2026','v01','v02')):
        raise ValueError('forbidden read path')
    return path.read_bytes()

def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()

def read(path):
    value=raw(path)
    return json.loads(gzip.decompress(value) if str(path).endswith('.gz') else value)

def value_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

label_study=SOURCE/'studies/B67-lag-matched-short-supervision'
loss_study=SOURCE/'studies/B88A-short-net-loss-families'
registration=read(loss_study/'registration.json')
manifest=read(DELIVERY/'models/manifest.json')
median_manifest={row['fold_year']:row for row in manifest if row['family']=='short_median'}
annual=[]
for year in range(2018,2026):
    labels_dir=label_study/'folds'/str(year)
    loss_dir=loss_study/'folds'/str(year)
    parent=read(labels_dir/'training.json')
    training=read(loss_dir/'training.json')
    banks=read(labels_dir/'labels.json.gz')
    ids=parent['common_ids']
    cut=(date(year-1,12,31)-date(2017,1,1)).days
    bank_ids={head:[row['index'] for row in bank] for head,bank in banks.items()}
    maps={head:{row['index']:row for row in bank} for head,bank in banks.items()}
    candidate_ids=bank_ids['L1']
    defined=[index for index in candidate_ids if all(maps[head][index]['status']=='DEFINED' for head in ('L1','L2'))]
    maturity_exact=all(row['maturity_index']==row['index']+60+int(head[-1]) for head,bank in banks.items() for row in bank)
    max_maturity=max((row['maturity_index'] for bank in banks.values() for row in bank),default=None)
    receipt_checks=[]
    for key, receipts in training['receipts'].items():
        for item in receipts:
            receipt_checks.append(item['cut']==cut and item['first']==ids[0] and item['last']==ids[-1] and item['count']==len(ids) and item['common_last_label']==ids[-1]+62 and item['common_last_label']<=cut-6)
    selected=[{'index':index,'L1':maps['L1'][index]['simple_return'],'L2':maps['L2'][index]['simple_return']} for index in ids]
    route=median_manifest[year]
    expected_names=sorted(Path(path).name for path in training['model_states'] if Path(path).name.startswith('MEDIAN_'))
    actual_names=sorted(Path(item['path']).name for item in route['files'])
    state_checks=[]
    for item in route['files']:
        name=Path(item['path']).name
        exported=DELIVERY/item['path']
        original=loss_dir/'models'/name
        state=read(exported)
        source_key='models/'+name
        state_checks.append({
            'file':item['path'],
            'export_manifest_digest':sha(exported)==item['sha256'],
            'source_training_digest':sha(original)==training['model_states'][source_key],
            'export_equals_source':sha(exported)==sha(original),
            'profile_matches':state['profile']==registration['profile'],
            'seed_registered':state['seed'] in registration['seeds'],
            'selected_loss':state['spec']=={'id':'MEDIAN','loss':'absolute_error','alpha':0.9},
            'feature_count':state['n_features']==44,
            'head_registered':state['execution_lag'] in (1,2),
            'label_kind':state['label_kind']=='SHORT_NET' and state['common_sample'] is True,
        })
    checks={
        'label_digest_matches_parent':sha(labels_dir/'labels.json.gz')==parent['labels_sha256'],
        'loss_label_digest_binding':training['source_labels_sha256']==(parent['labels_sha256'] if ids else None),
        'head_candidate_ids_equal':bank_ids['L1']==bank_ids['L2'],
        'common_ids_exact_defined_intersection':ids==defined,
        'loss_common_ids_equal':training['common_ids']==ids,
        'common_ids_strict_and_warmup':not ids or (ids[0]>=252 and all(a<b for a,b in zip(ids,ids[1:]))),
        'all_label_maturity_exact':maturity_exact,
        'all_labels_within_cut_minus6':max_maturity is None or max_maturity<=cut-6,
        'all_fit_receipts_match_ids_cut':all(receipt_checks),
        'median_export_exact_state_roster':actual_names==expected_names,
        'median_export_all_state_checks':all(all(value for key,value in item.items() if key!='file') for item in state_checks),
        'unavailable_matches_empty_ids':route['missing']==(len(ids)==0),
    }
    annual.append({'fold_year':year,'cut':cut,'common_id_count':len(ids),'common_ids_sha256':value_sha(ids),
        'selected_two_head_label_vector_sha256':value_sha(selected),'candidate_bank_row_count_per_head':len(candidate_ids),
        'max_label_maturity_index':max_maturity,'embargo_last_allowed_index':cut-6,
        'selected_median_state_count':len(state_checks),'checks':checks,'state_checks':state_checks,'all_checks_pass':all(checks.values())})

forbidden_payload_keys={'labels','common_ids','maturity_index','simple_return','labels_sha256','model_states'}
context_checks=[]
def inspect_keys(value,location=''):
    found=[]
    if isinstance(value,dict):
        for key,item in value.items():
            if key in forbidden_payload_keys:
                found.append(location+'/'+key)
            found.extend(inspect_keys(item,location+'/'+key))
    elif isinstance(value,list):
        for index,item in enumerate(value):
            if isinstance(item,(dict,list)):
                found.extend(inspect_keys(item,location+'/'+str(index)))
    return found
for name in ('high_return','budget','sizing','median'):
    value=read(DELIVERY/'artifacts/contexts'/f'{name}.json.gz')
    context_checks.append({'name':name,'top_level_type':type(value).__name__,'top_level_count':len(value),
        'training_payload_key_hits':inspect_keys(value)})

code_files=('lagged_short.py','short_loss_models.py','boosted_stop.py','short_payoff.py')
frozen_copy_matches={name:sha(SOURCE/'lab'/name)==sha(DELIVERY/'src/btc_strategy/_frozen/lab'/name) for name in code_files}
result={'round':3,'source_annual_label_and_export_checks':annual,'all_annual_checks_pass':all(row['all_checks_pass'] for row in annual),
    'median_export_model_total':sum(row['selected_median_state_count'] for row in annual),
    'context_payload_key_checks':context_checks,'selected_frozen_source_copy_hash_matches':frozen_copy_matches,
    'training_data_export_paths_seen':[str(p.relative_to(DELIVERY)) for root in (DELIVERY/'models',DELIVERY/'artifacts') for p in root.rglob('*') if p.is_file() and any(token in p.name.lower() for token in ('label','training','seal','receipt','common_ids'))],
    'executed_research_code':False,'refitted_models':False,'source_or_delivery_written':False,
    'implementation_access_isolation_tested':False,'snapshot_limitation':'delivery tree is under construction; observations apply only to this read snapshot'}
with (OWN/'checks-r03.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(json.dumps({'all_annual_checks_pass':result['all_annual_checks_pass'],'median_export_model_total':result['median_export_model_total'],
    'annual_summary':[{key:value for key,value in row.items() if key!='state_checks'} for row in annual],
    'contexts':context_checks,'source_copy_matches':frozen_copy_matches,'training_export_paths_seen':result['training_data_export_paths_seen']},ensure_ascii=False,indent=2))
