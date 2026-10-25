"""Independent repository replay; never writes frozen benchmark accounts."""
import argparse,json,hashlib
from .artifacts import catalog,read
from .strategies import compose,verify_targets
from .execution import run_account
from .costs import CASES,BORROW
from ._runtime.carry_audit import audit
from ._runtime.quote_exposure import measure


def run(name,case,use_models=True):
 verify_targets(name)
 if use_models:
  from .models import rebuild_context
  days,prices,targets,entry=compose(name,rebuild_context(name))
  expected=read('artifacts/targets/'+name+'.json.gz');assert targets==expected['targets']and entry==expected['entry_permission']
 else:days,prices,targets,entry=compose(name)
 a=run_account(days,prices,targets,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
 original=read('artifacts/accounts/'+name+'/'+case+'.json.gz')
 if a!=original:raise AssertionError(name+'/'+case+' complete native account mismatch')
 proof=audit(a,days,prices,targets,CASES[case],BORROW[case],{},entry,False)
 x=measure(a,CASES[case][0])
 scopes={
  'summary.max_gross_exposure_pct':'maximum whole-position gross at daily post-fill marks; percent of adjusted equity',
  'summary.average_gross_exposure_pct':'average whole-position gross at daily post-fill marks; percent of adjusted equity',
  'summary.max_drawdown_pct':'continuous-account daily adjusted-equity peak-to-trough drawdown; percent',
  'max_daily_short_gross':'maximum short gross at daily before-or-after-order proxy points; percent of adjusted equity',
  'max_daily_whole_gross':'maximum whole-position gross at daily before-or-after-order proxy points; percent of adjusted equity',
 }
 return dict(strategy=name,case=case,complete_account_exact=True,independent_decimal=proof,summary=a['summary'],max_daily_short_gross=x['before_or_after_short'],max_daily_whole_gross=x['before_or_after_whole'],forecasts_reconstructed_from_numeric_models=use_models,metric_scope=scopes,risk_qualification=x['qualification']+'; entry budgets and stop triggers are not continuous-exposure or fill-loss caps')


def main():
 p=argparse.ArgumentParser();p.add_argument('--strategy',choices=[r['id']for r in catalog()]);p.add_argument('--case',choices=list(CASES));p.add_argument('--all',action='store_true');p.add_argument('--cached-forecasts',action='store_true');a=p.parse_args()
 if not a.all and not a.strategy:p.error('--strategy or --all required')
 names=[a.strategy]if a.strategy else[r['id']for r in catalog()]
 for name in names:
  for case in([a.case]if a.case else CASES):print(json.dumps(run(name,case,not a.cached_forecasts),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
