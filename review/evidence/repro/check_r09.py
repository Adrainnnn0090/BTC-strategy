"""Round 09 nine strategy cards versus 36 frozen books; no replay or training."""
import ast
import gzip
import hashlib
import json
import re
from pathlib import Path

SOURCE=Path('/workspace/BTCStrategyResearchLedger')
ROOT=Path('/workspace/BTC-strategy')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')

def raw(path):
    if any(token in str(path).lower() for token in ('2026','v01','v02')):
        raise ValueError('forbidden economic file path')
    return Path(path).read_bytes()
def sha(path):return hashlib.sha256(raw(path)).hexdigest()
def read(path):
    data=raw(path)
    return json.loads(gzip.decompress(data) if str(path).endswith('.gz') else data)

catalog=read(ROOT/'artifacts/catalog.json')
index=(ROOT/'strategies/README.md').read_text()
tree=ast.parse(raw(ROOT/'src/btc_strategy/models.py'))
wiring=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='rebuild_context')
calls=[]
def context(name):return [{'scores':{}},{'scores':{}},{'scores':{}},{}]
def rebuilt(family):calls.append(family);return ('synthetic-placeholder',)
namespace={'context':context,'_rebuilt':rebuilt}
exec(compile(ast.fix_missing_locations(ast.Module(body=[wiring],type_ignores=[])),'<synthetic-wiring>','exec'),namespace)

cards=[];books=[]
for item in catalog['strategies']:
    name=item['id'];path=ROOT/'strategies'/item['category']/name.lower()/'README.md'
    text=path.read_text()
    calls.clear();namespace['rebuild_context'](name)
    families=sorted(set(calls))
    family_match=re.search(r'模型家族：([^。]+)',text)
    stated_families=sorted(part.strip() for part in family_match.group(1).split(',')) if family_match else []
    values={label:float(re.search(r'\|'+re.escape(label)+r'\|([+\-\d.]+)%\|',text).group(1)) for label in ('STRESS累计净收益','四成本最差日度峰谷回撤','DELAY累计净收益')}
    for case in ('BASE','STRESS','SEVERE','DELAY'):
        artifact=ROOT/'artifacts/accounts'/name/(case+'.json.gz')
        origin=SOURCE/item['source_study']/'accounts'/item['recipe']['id']/(case+'.json.gz')
        account=read(artifact);summary=account['summary']
        peak=100.;dd=0.
        for mark in account['marks']:
            equity=float(mark['equity']);peak=max(peak,equity);dd=max(dd,1-equity/peak)
        annual=[];prior=100
        for year in sorted({mark['date'][:4] for mark in account['marks']}):
            ending=float([mark for mark in account['marks'] if mark['date'].startswith(year)][-1]['equity'])
            annual.append({'year':year,'return_pct':100*(ending/prior-1)});prior=ending
        positive=sorted((float(trade['pnl']) for trade in account['trades'] if not trade['terminal'] and float(trade['pnl'])>0),reverse=True)
        concentration=sum(positive[:2])/sum(positive) if positive else None
        books.append({'strategy':name,'case':case,'source_path':str(origin.relative_to(SOURCE)),
            'artifact_source_bytes_equal':sha(artifact)==sha(origin),
            'catalog_summary_exact':item['metrics'][case]==summary,
            'daily_drawdown_recomputed_exact':summary['max_drawdown_pct']==100*dd,
            'annual_recomputed_exact':summary['annual']==annual,
            'positive_trade_top2_fraction_recomputed_exact':summary['best_two_positive_contribution_fraction']==concentration,
            'account_period_exact':account['marks'][0]['date']==catalog['period'][0] and account['marks'][-1]['date']==catalog['period'][1]})
    worst=max(value['max_drawdown_pct'] for value in item['metrics'].values())
    dd_case=[case for case,value in item['metrics'].items() if value['max_drawdown_pct']==worst]
    links=re.findall(r'\]\(([^)]+)\)',text)
    cards.append({'strategy':name,'card_path':str(path.relative_to(ROOT)),'card_sha256':sha(path),
        'card_title_exact':text.startswith('# '+name+'\n'),
        'period_2018_2025_stated':'2018—2025' in text,
        'STRESS_rounded5_exact':values['STRESS累计净收益']==float(f"{item['metrics']['STRESS']['return_pct']:.5f}"),
        'worst4_daily_DD_rounded5_exact':values['四成本最差日度峰谷回撤']==float(f'{worst:.5f}'),
        'worst_DD_case':dd_case,
        'DELAY_rounded5_exact':values['DELAY累计净收益']==float(f"{item['metrics']['DELAY']['return_pct']:.5f}"),
        'new2026_validation_text_false':'尚无新2026验证' in text and 'No new 2026 validation' in item['validation'],
        'catalog_explicit_validation_false_boolean':any(key in item and item[key] is False for key in ('new2026validation','new_2026_validation')),
        'shared_model_families_exact':stated_families==families,
        'card_stated_families':stated_families,
        'catalog_structured_model_families_present':any(key in item for key in ('model_families','models')),
        'catalog_source_study':item['source_study'],'catalog_local_recipe_id':item['recipe']['id'],
        'source_study_explicit_in_card':item['source_study'] in text,
        'source_local_id_explicit_in_card':bool(re.search(r'(原|local|recipe|来源).*'+re.escape(item['recipe']['id']),text,re.I)),
        'explicit_cost_parameter_or_cost_table_link':bool(re.search(r'手续费|滑点|融资|borrow|costs\.py|COSTS|成本假设',text,re.I)),
        'annual_breakdown_or_link_in_card':bool(re.search(r'逐年|年度收益|annual|年度明细',text,re.I)),
        'positive_trade_concentration_or_link_in_card':bool(re.search(r'集中|最大两|最大2|best_two|concentration',text,re.I)),
        'all_existing_relative_links_resolve':all((path.parent/link).resolve().exists() for link in links if not link.startswith(('http:','https:','#'))),
        'C02_C04_eligibility_2020_2025_and_new_entries':name not in ('C02','C04') or ('2020–2025' in text and '0.75' in text and '新开' in text),
        'namespaced_B88A_card_and_catalog':name!='B88A_S03' or (item['source_study']=='studies/B88A-short-net-loss-families' and item['recipe']['id']=='S03' and '# B88A_S03' in text)})

eligibility=[]
for year in range(2018,2026):
    training=read(SOURCE/'studies/B31-constant-sizing-controls/folds'/str(year)/'training.json')
    eligibility.append({'fold_year':year,'Y01':training['active']['Y01'],'Y04':training['active']['Y04'],'matches_2020_onward':training['active']=={'Y01':year>=2020,'Y04':year>=2020}})
core_keys=('card_title_exact','period_2018_2025_stated','STRESS_rounded5_exact','worst4_daily_DD_rounded5_exact','DELAY_rounded5_exact','new2026_validation_text_false','shared_model_families_exact','all_existing_relative_links_resolve','C02_C04_eligibility_2020_2025_and_new_entries','namespaced_B88A_card_and_catalog')
book_keys=('artifact_source_bytes_equal','catalog_summary_exact','daily_drawdown_recomputed_exact','annual_recomputed_exact','positive_trade_top2_fraction_recomputed_exact','account_period_exact')
result={'round':9,'catalog_period':catalog['period'],'card_count':len(cards),'book_count':len(books),
    'nine_cards':cards,'thirty_six_benchmark_comparisons':books,
    'all_core_card_checks_pass':all(all(card[key] for key in core_keys) for card in cards),
    'all_book_checks_pass':all(all(book[key] for key in book_keys) for book in books),
    'catalog_root_structured_costs_present':any(key in catalog for key in ('costs','cost_assumptions','cases')),
    'catalog_root_explicit_new2026validation_false':any(key in catalog and catalog[key] is False for key in ('new2026validation','new_2026_validation')),
    'global_index_disambiguates_B88A_from_B51':'B88A_S03' in index and '旧B51同名' in index,
    'global_index_rejects_shared_high_return_independent_alpha':'不能当作独立alpha组合' in index,
    'C02_C04_source_eligibility':eligibility,
    'missing_fields_by_card':{card['strategy']:[key for key in ('catalog_explicit_validation_false_boolean','catalog_structured_model_families_present','source_study_explicit_in_card','explicit_cost_parameter_or_cost_table_link','annual_breakdown_or_link_in_card','positive_trade_concentration_or_link_in_card') if not card[key]] for card in cards},
    'new_model_or_account_execution':False,'boundary_regression_or_independent_environment_test':False,
    'source_or_delivery_written':False,'forbidden_economic_data_read':False,
    'limitation':'Stored-book arithmetic/documentation parity only; not an independent native replay, external market benchmark, or fresh validation.'}
with (OWN/'checks-r09.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({key:result[key] for key in ('card_count','book_count','all_core_card_checks_pass','all_book_checks_pass','catalog_root_structured_costs_present','catalog_root_explicit_new2026validation_false','global_index_disambiguates_B88A_from_B51','C02_C04_source_eligibility','missing_fields_by_card')},ensure_ascii=False,indent=2))
