"""One fixed ETHshort forecast fusion and two exact null fusion controls."""
import argparse,subprocess,sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b87_io import STUDY,UPSTREAM,install_guard
from .b86 import RECIPES as OLD_RECIPES,assemble as old_assemble,targets as old_targets
from .eth_short_transfer import GROUPS
from .price_trail_activation import frame
from .short_forecast_fusion import half_mean
from .conditional_short import component
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id=f'F{i+1:02}',kind='NULL_FUSION'if i<2 else'ETH_FUSION',stream=g)for i,g in enumerate(GROUPS)]+[dict(id=r['id'],kind='LEGACY')for r in OLD_RECIPES]
SOURCES=('lab/b87.py','lab/b87_io.py','lab/short_forecast_fusion.py','tools/verify_b87.py','tests/test_b87.py',
 'notes/proposed-fixed-eth-short-fusion.md','studies/B87-fixed-eth-short-fusion/spec.md')


def freeze():
    p=read(UPSTREAM/'registration.json');v=read(UPSTREAM/'verification.json');a=read(UPSTREAM/'analysis.json')
    assert v['status']=='PASS'and v['final_members']==294 and v['exact_controls']==24 and v['results_sha256']==sha(UPSTREAM/'results.json')and not v['validation_read']
    for n in ('E01','E02'):
        m=a['descriptive_mechanism_checks'][n];assert m['targets_exact_p02']and m['long_flat_permissions_exact']and m['added_postshort_permission_decisions']==m['removed_postshort_permission_decisions']==0
    code={f:d for f,d in {**p['sources'],**p['inherited_sources']}.items()if not f.startswith('studies/')};assert all(sha(ROOT/f)==d for f,d in code.items())
    binding=dict(p['source'])
    for n in ('registration.json','verification.json','analysis.json','results.json'):
        q=UPSTREAM/n;binding[str(q.relative_to(ROOT))]=sha(q)
    for year in range(2018,2026):
        for n in ('training.json','seal.json','predictions.json.gz','test-receipt.json'):
            q=UPSTREAM/'folds'/str(year)/n;binding[str(q.relative_to(ROOT))]=sha(q)
    for recipe in OLD_RECIPES:
        for case in CASES:
            q=UPSTREAM/'accounts'/recipe['id']/f'{case}.json.gz';binding[str(q.relative_to(ROOT))]=sha(q)
    write(STUDY/'registration.json',dict(recipes=RECIPES,groups=GROUPS,source=binding,inherited_sources=code,sources={f:sha(ROOT/f)for f in SOURCES},versions=p['versions'],project_runtime_sources=p['project_runtime_sources'],
        manifest_sha256=p['manifest_sha256'],costs=CASES,financing=BORROW,model_fits=0,calibration_accounts=0,weight=.5,accounts=48,exact_legacy_controls=36,exact_null_controls=8,exact_controls=44,
        prescribed_replay=['F03','DELAY'],target_return_pct=10000,strict_drawdown_pct=35,strict_PIT=False,validation_read=False,
        qualification='fixed 50/50same-targetshortforecastfusion;oneactualhypothesis/twonullcontrols;originalP02long/risk;conditionalETH;consumed2018–2025;all2026excluded'))
    print('B87 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['recipes']==RECIPES and reg['groups']==list(GROUPS)and len(RECIPES)==12 and reg['weight']==.5
    assert sha(FOLDS/'manifest.json')==reg['manifest_sha256']and reg['costs']=={k:list(v)for k,v in CASES.items()}and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for f,d in reg['project_runtime_sources'].items():assert sha(f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def source_fold(reg,year):
    folder=UPSTREAM/'folds'/str(year);tr=bound(reg,folder/'training.json');seal=bound(reg,folder/'seal.json');receipt=bound(reg,folder/'test-receipt.json');f=bound(reg,folder/'predictions.json.gz')
    assert tr['cutoff']==seal['cutoff']==f'{year-1}-12-31'and not seal['current_test_read']and seal['training_sha256']==sha(folder/'training.json')and seal['registration_sha256']==sha(UPSTREAM/'registration.json')
    assert receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')and receipt['fitting_calls']==receipt['selection_calls']==0 and not receipt['validation_read']
    assert receipt['test_sha256']==sha(FOLDS/str(year)/'test.json')and f['dates']==f['fixed']['dates']and f['dates'][0]==f'{year-1}-12-31'and f['dates'][-1]==f'{year}-12-30'
    return tr,f


def train(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'train');verify(reg);folder=STUDY/'folds'/str(year)
    tr=bound(reg,UPSTREAM/'folds'/str(year)/'training.json');seal=bound(reg,UPSTREAM/'folds'/str(year)/'seal.json')
    assert tr['cutoff']==seal['cutoff']==f'{year-1}-12-31'and not seal['current_test_read']and seal['training_sha256']==sha(UPSTREAM/'folds'/str(year)/'training.json')
    trainsha=sha(FOLDS/str(year)/'train.json')
    write(folder/'training.json',dict(year=year,cutoff=tr['cutoff'],parent_policy=tr['y01_policy'],source_training_sha256=sha(UPSTREAM/'folds'/str(year)/'training.json'),
        model_fits=0,selection_calls=0,calibration_accounts=0,weight=.5,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(cutoff=tr['cutoff'],training_sha256=sha(folder/'training.json'),train_sha256=trainsha,registration_sha256=sha(STUDY/'registration.json'),current_test_read=False));print('B87 TRAIN',year,flush=True)


def test(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'test');verify(reg);folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json')
    assert seal['training_sha256']==sha(folder/'training.json')and seal['registration_sha256']==sha(STUDY/'registration.json')and not seal['current_test_read']
    parent,f=source_fold(reg,year);assert parent['y01_policy']==tr['parent_policy'];scores={g:half_mean(f['fixed']['learner'],f['scores'][g])for g in GROUPS}
    write(folder/'predictions.json.gz',dict(dates=f['dates'],scores=scores,fixed=f['fixed']));write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),
        source_predictions_sha256=sha(UPSTREAM/'folds'/str(year)/'predictions.json.gz'),source_receipt_sha256=sha(UPSTREAM/'folds'/str(year)/'test-receipt.json'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)));print('B87 TEST',year,flush=True)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)};records={};policies={};scores={g:[None]*len(days)for g in GROUPS}
    for year in range(2018,2026):
        folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json');receipt=read(folder/'test-receipt.json');f=read(folder/'predictions.json.gz')
        assert seal['training_sha256']==sha(folder/'training.json')and receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')
        source_fold(reg,year);records[year]=f['fixed'];policies[year]=tr['parent_policy']
        for g in GROUPS:
            for d,v in zip(f['dates'],f['scores'][g],strict=True):scores[g][where[d]]=v
    values,counts=frame(days,prices,records,policies);old=old_assemble(reg);assert values==old[0]
    return values,scores,old


def targets(assembled,recipe):
    values,scores,old=assembled
    if recipe['kind']=='LEGACY':return old_targets(old,next(r for r in OLD_RECIPES if r['id']==recipe['id']))
    return component(values['days'],values['prices'],values['scores'],{'Y01':values['policies']},values['flags'],scores[recipe['stream']],.5,'MODEL')


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard(2025,'replay');verify(reg);assembled=assemble(reg);days,prices=assembled[0]['days'],assembled[0]['prices'];out=[]
    for recipe in RECIPES:
        target,entry=targets(assembled,recipe);ss={};failures={};audits={}
        for case in CASES:
            try:a=run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as e:failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(a,days,prices,target,CASES[case],BORROW[case],{},entry,False)
            if recipe['kind']in ('LEGACY','NULL_FUSION'):
                n='P02'if recipe['kind']=='NULL_FUSION'else recipe['id'];assert a==bound(reg,UPSTREAM/'accounts'/n/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct']for s in ss.values()),default=None);passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,summaries=ss,failures=failures,audits=audits,goal_gate=passed));print('B87 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,strict_PIT=False,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'));p.add_argument('--year',type=int);a=p.parse_args()
    if a.command in ('train','test'):
        if a.year is None:p.error('--year required')
        globals()[a.command](a.year)
    elif a.command=='run':
        for year in range(2018,2026):
            for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b87',stage,'--year',str(year)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b87','replay'],cwd=ROOT,check=True)
    else:globals()[a.command]()
