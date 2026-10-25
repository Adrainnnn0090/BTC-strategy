"""Independent pre/post quote inventory coverage and constant-budget eligibility audit."""
import ast
import gzip
import hashlib
import json
import math
from datetime import date, timedelta
from decimal import Decimal as D
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

NEW = Path('/workspace/BTC-strategy')
SOURCE = Path('/workspace/BTCStrategyResearchLedger')
OUTPUT = Path('/workspace/BTCExpertReview/workspaces/data/r07-checks.json')
CASES = dict(BASE=('.001',1), STRESS=('.003',1), SEVERE=('.005',1), DELAY=('.003',2))


def read(path):
    assert not any(part in path.parts for part in ('2026','review','verification','V01-2026-retained-validation','V02-buy-and-hold-validation'))
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(relative,names,namespace):
    module=ast.parse((SOURCE/relative).read_text())
    nodes=[node for node in module.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names]
    assert {node.name for node in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),relative,'exec'),namespace)
    return namespace


def point(day,phase,signed,p,equity):
    assert equity>0
    return dict(date=day,phase=phase,signed_quantity=str(signed),
                equity=str(equity),gross_pct=float(100*abs(signed)*p/equity))


market=read(NEW/'artifacts/factors/market.json.gz')
days,prices=market['days'],market['prices']
where={day:i for i,day in enumerate(days)}
catalog=read(NEW/'artifacts/catalog.json')['strategies']
exposures=[]
for strategy in catalog:
    for case,(fee_text,lag) in CASES.items():
        account=read(NEW/f'artifacts/accounts/{strategy["id"]}/{case}.json.gz')
        byday={fill['date']:fill for fill in account['fills']}
        finance={row['date']:D(row['cost']) for row in account['financing']}
        assert len(byday)==len(account['fills']) and len(finance)==len(account['financing'])
        fee=D(fee_text);cash=D(100);debt=D(0);position=None
        before=[];after=[];exit_points=[];cross_year=[];max_pre_post_equity_error=D(0)
        for mark in account['marks']:
            p=D(str(mark['reference_price']));bid=D(mark['bid']);ask=D(mark['ask'])
            debt+=finance.get(mark['date'],D(0))
            prior_signed=D(0)
            if position:
                prior_signed=position['side']*position['q']
                quote=bid if prior_signed>0 else ask
                unrealized=prior_signed*(quote-position['entry_price'])
                reserve=position['q']*quote*fee
                pre_equity=cash-debt+unrealized-reserve
                pre=point(mark['date'],'before_order',prior_signed,p,pre_equity)
                before.append(pre)
                max_pre_post_equity_error=max(max_pre_post_equity_error,abs(pre_equity-D(mark['equity'])))
                assert abs(pre_equity-D(mark['equity']))<=D('.00000002')
                if mark['date'].endswith('-01-01'):
                    cross_year.append(dict(date=mark['date'],carried_from=position['entry_date'],quantity=str(prior_signed)))
            fill=byday.get(mark['date'])
            if fill:
                q,fill_price,charged=D(fill['quantity']),D(fill['price']),D(fill['fee'])
                if fill['action']=='OPEN':
                    assert position is None
                    cash-=charged
                    position=dict(side=1 if fill['side']=='BUY' else -1,q=q,entry_price=fill_price,entry_date=mark['date'])
                else:
                    assert position and q==position['q']
                    cash+=position['side']*q*(fill_price-position['entry_price'])-charged
                    exit_points.append(dict(**pre,exit_reason=fill['reason'],post_fill_gross_pct=0.))
                    position=None
            signed=D(0) if position is None else position['side']*position['q']
            assert signed==D(mark['signed_qty'])
            assert D(mark['raw_cash'])==cash and D(mark['financing_total'])==debt
            if prior_signed:
                assert signed in (prior_signed,D(0))
            post=point(mark['date'],'after_fill',signed,p,D(mark['equity']))
            after.append(post)
            if fill and fill['action']=='CLOSE':
                assert signed==0 and pre['gross_pct']>0
        assert position is None
        highest=lambda points,short=False:max((item for item in points if not short or D(item['signed_quantity'])<0),key=lambda item:item['gross_pct'],default=dict(date=None,gross_pct=0.))
        post_whole,post_short=highest(after),highest(after,True)
        both_whole,both_short=highest(before+after),highest(before+after,True)
        assert abs(post_whole['gross_pct']-account['summary']['max_gross_exposure_pct'])<=1e-8
        assert both_whole['gross_pct']>=post_whole['gross_pct'] and both_short['gross_pct']>=post_short['gross_pct']
        exposures.append(dict(strategy=strategy['id'],case=case,post_fill_whole=post_whole,
                              post_fill_short=post_short,before_or_after_whole=both_whole,before_or_after_short=both_short,
                              close_days_omitted_by_post_only=len(exit_points),
                              risk_close_days_omitted_by_post_only=sum(item['exit_reason'] in ('STOP_LOSS','TRAIL_STOP','TAKE_PROFIT') for item in exit_points),
                              highest_exit_day=highest(exit_points),
                              max_equity_reconciliation_error=str(max_pre_post_equity_error),
                              carried_new_year_points=len(cross_year),cross_year_examples=cross_year[:2]))

# Reconstruct unscaled long parents from the original pure signal rules.
forecast_year=extract('lab/b05.py',('forecast_year',),{})['forecast_year']
feature_ns=extract('lab/signals.py',('valid','Features'),dict(np=np,pd=pd,lru_cache=lru_cache))
SignalFactory=extract('lab/b12_signals.py',('SignalFactory',),dict(Features=feature_ns['Features'],math=math,forecast_year=forecast_year))['SignalFactory']
permissions=extract('lab/entry_permissions.py',('permissions',),dict(math=math,forecast_year=forecast_year,GATES=('POS1','POS3')))['permissions']
desired=extract('lab/exit_coordinate.py',('desired',),dict(SignalFactory=SignalFactory,permissions=permissions))['desired']
sizing=read(NEW/'artifacts/contexts/sizing.json.gz')
assert sizing[0]==days and sizing[1]==prices
scores,policies,choices,active=sizing[2],sizing[3],sizing[4],sizing[6]
base_policies={int(year):value for year,value in policies['U02'].items()}
patched={year:{**value,**{key:setting for key,setting in choices['H03'][str(year)].items() if setting is not None}} for year,value in base_policies.items()}
h03=[None if a is None or b is None else .5*(a+b) for a,b in zip(scores['CAL44_STOP'],scores['BASE_TREE'],strict=True)]
parent_targets={}
parent_targets['C02']=desired(days,prices,h03,patched)
parent_targets['C04']=desired(days,prices,scores['EXTRA_DYNAMICS_L60'],base_policies)
expected_active={key:[False]*len(days) for key in ('Y01','Y04')}
eligibility=[]
for year in range(2018,2026):
    folder=SOURCE/f'studies/B31-constant-sizing-controls/folds/{year}'
    training,seal,forecast=[read(folder/name) for name in ('training.json','seal.json','predictions.json.gz')]
    assert training['cutoff']==seal['cutoff']==f'{year-1}-12-31' and not seal['current_test_read']
    assert seal['training_sha256']==sha(folder/'training.json')
    assert forecast['active']==training['active']
    assert all(training['active'][key]==(training['rank_counts'][key]['positive']>=128)==(year>=2020) for key in expected_active)
    for day in forecast['dates']:
        assert forecast_year(day)==year
        for key in expected_active:
            expected_active[key][where[day]]=training['active'][key]
    eligibility.append(dict(fold_year=year,cutoff=training['cutoff'],active=training['active'],
                            positive_forecasts={key:training['rank_counts'][key]['positive'] for key in expected_active}))
assert active==expected_active
constants=[]
for identifier,key,parent_id in (('C02','Y01','C11'),('C04','Y04','C12')):
    packet=read(NEW/f'artifacts/targets/{identifier}.json.gz')
    raw_targets,raw_permissions=parent_targets[identifier]
    assert packet['entry_permission']==raw_permissions
    for i,(target,parent) in enumerate(zip(packet['targets'],raw_targets,strict=True)):
        expected={**parent,'long_fraction':parent['long_fraction']*(.75 if active[key][i] else 1.)}
        assert target==expected
    dates_active=[day for day,flag in zip(days,active[key],strict=True) if flag]
    assert dates_active[0]=='2019-12-31' and dates_active[-1]=='2025-12-30' and len(dates_active)==2192
    per_case=[]
    for case,(_,lag) in CASES.items():
        scaled=read(NEW/f'artifacts/accounts/{identifier}/{case}.json.gz')
        unscaled=read(SOURCE/f'studies/B31-constant-sizing-controls/accounts/{parent_id}/{case}.json.gz')
        scaled_fills,unscaled_fills=scaled['fills'],unscaled['fills']
        assert [(row['date'],row['action'],row['side'],row['reason']) for row in scaled_fills]==[(row['date'],row['action'],row['side'],row['reason']) for row in unscaled_fills]
        assert [row for row in scaled['marks'] if row['date']<'2020-01-01']==[row for row in unscaled['marks'] if row['date']<'2020-01-01']
        opens=[row for row in scaled_fills if row['action']=='OPEN']
        reduced=[row for row in opens if active[key][row['index']-lag]]
        identity=[row for row in opens if not active[key][row['index']-lag]]
        assert all(int(row['date'][:4]) in (2018,2019) for row in identity)
        assert all(int(row['date'][:4])>=2020 for row in reduced)
        per_case.append(dict(case=case,openings=len(opens),reduced_openings=len(reduced),identity_openings=len(identity),
                             first_reduced_open=reduced[0]['date'] if reduced else None,
                             cold_2018_2019_marks_exact_to_unscaled_parent=True,entry_exit_dates_reasons_exact=True))
    constants.append(dict(strategy=identifier,parent_active_key=key,active_signal_first=dates_active[0],
                          active_signal_last=dates_active[-1],active_signal_rows=len(dates_active),
                          unused_2025_12_31_tail_active=active[key][-1],target_fields_exact_except_registered_long_fraction=True,
                          per_case=per_case))

result=dict(status='PASS',exposure_accounts=36,exposures=exposures,eligibility=eligibility,constants=constants,
            total_exit_days_lost_by_post_only=sum(row['close_days_omitted_by_post_only'] for row in exposures),
            total_risk_exit_days_lost_by_post_only=sum(row['risk_close_days_omitted_by_post_only'] for row in exposures),
            accounts_with_whole_max_understated_by_post_only=sum(row['before_or_after_whole']['gross_pct']>row['post_fill_whole']['gross_pct'] for row in exposures),
            accounts_with_short_max_understated_by_post_only=sum(row['before_or_after_short']['gross_pct']>row['post_fill_short']['gross_pct'] for row in exposures),
            limitations=['These are daily proxy quotes before/after orders, not an intraday maximum or future exposure cap.',
                         'Budget multipliers apply to eligible fresh entries; quantities are not rebalanced while held.',
                         'Existing fills were read and inventories reconstructed; no writer, native engine, fitting or parameter search was run.',
                         'No 2026 economic data, expert opinions, review artifacts or verification conclusions were read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('exposures','eligibility')},ensure_ascii=False,indent=2))
