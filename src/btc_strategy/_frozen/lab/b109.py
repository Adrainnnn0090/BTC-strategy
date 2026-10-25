"""Entry-owned long profit cap on fixed TS04 entries and annual forecasts."""
import argparse,subprocess,sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b109_io import STUDY,PROOF,PARENT,SOURCE,SHORT,CARRY,ANCHOR,LEGACY,install_guard
from .b82 import bundle
from .price_trail_activation import frame
from .long_profit_local_coordinate import ARMS,patch_risk
from .cold_short_profit_trailing import ARMS as PARENT_TRAIL_ARMS,patch_risk as parent_trail
from .shorter_cold_momentum import ARMS as SHORT_ENTRY_ARMS,patch_entry as shorter_entry
from .cold_entry_momentum import ARMS as ORIGINAL_ENTRY_ARMS,patch_entry as original_entry
from .faster_cold_short import ARMS as ORIGINAL_COLD_ARMS,apply_cold_gate as original_cold_gate
from .long_vol_budget import patch_budget
from .patient_profit_exit import ARMS as PROFIT_ARMS,patch_profit_exit
from .full_retained import load_bank
from .conditional_short import component
from .b64a import RECIPES as OLD_RECIPES,targets as old_targets
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id=a['id'],kind='LONG_PROFIT',arm=a)for a in ARMS]+[dict(id=n,kind='LEGACY')for n in LEGACY]
SOURCES=('lab/b109.py','lab/b109_io.py','lab/long_profit_local_coordinate.py','tools/verify_b109.py','tests/test_b109.py',
 'notes/proposed-long-profit-local-coordinate.md','studies/B109-long-profit-local-coordinate/spec.md','studies/B109-long-profit-local-coordinate/checks.json')


def freeze():
    p=read(PROOF/'registration.json');v=read(PROOF/'verification.json');assert v['status']=='PASS'and v['accounts']==64 and v['exact_controls']==48 and v['independent_reference_target_audits']==16 and not v['validation_read']
    code={f:d for f,d in {**p['sources'],**p['inherited_sources']}.items()if not f.startswith('studies/')};assert all(sha(ROOT/f)==d for f,d in code.items())
    runtime=p['project_runtime_sources'];assert all(sha(f)==d for f,d in runtime.items());binding={}
    for base in (PARENT,SOURCE,SHORT,CARRY,ANCHOR,PROOF):
        q=base/'registration.json';binding[str(q.relative_to(ROOT))]=sha(q)
    for base in (PARENT,SHORT,CARRY,ANCHOR,PROOF):
        q=base/'verification.json';binding[str(q.relative_to(ROOT))]=sha(q)
    for year in range(2018,2026):
        for base in (PARENT,SOURCE,SHORT,CARRY):
            for n in ('training.json','seal.json','predictions.json.gz','test-receipt.json'):
                q=base/'folds'/str(year)/n;binding[str(q.relative_to(ROOT))]=sha(q)
    for base,n in LEGACY.values():
        for case in CASES:
            q=base/'accounts'/n/f'{case}.json.gz';binding[str(q.relative_to(ROOT))]=sha(q)
    write(STUDY/'registration.json',dict(arms=ARMS,recipes=RECIPES,source=binding,inherited_sources=code,sources={f:sha(ROOT/f)for f in SOURCES},versions=p['versions'],project_runtime_sources=runtime,
        manifest_sha256=sha(FOLDS/'manifest.json'),costs=CASES,financing=BORROW,model_fits=0,calibration_accounts=0,accounts=64,exact_controls=48,prescribed_replay=['LP50','DELAY'],
        reference_target_audits=16,target_return_pct=10000,strict_drawdown_pct=35,validation_read=False,qualification='long entry-owned profit cap only;allTS04signals-permissions-budgets-stops-shortrisk exact;consumed2018–2025;all2026excluded'))
    print('B109 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['arms']==list(ARMS)and reg['recipes']==RECIPES and len(RECIPES)==16
    assert sha(FOLDS/'manifest.json')==reg['manifest_sha256']and reg['costs']=={k:list(v)for k,v in CASES.items()}and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for f,d in reg['project_runtime_sources'].items():assert sha(f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def train(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'train');verify(reg);folder=STUDY/'folds'/str(year)
    tr=bound(reg,SOURCE/'folds'/str(year)/'training.json');seal=bound(reg,SOURCE/'folds'/str(year)/'seal.json')
    assert seal['cutoff']==tr['cutoff']==f'{year-1}-12-31'and not seal['current_test_read']and seal['training_sha256']==sha(SOURCE/'folds'/str(year)/'training.json')
    trainsha=sha(FOLDS/str(year)/'train.json')
    write(folder/'training.json',dict(year=year,cutoff=tr['cutoff'],parent_policy=tr['y01_policy'],model_fits=0,selection_calls=0,calibration_accounts=0,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(cutoff=tr['cutoff'],training_sha256=sha(folder/'training.json'),train_sha256=trainsha,registration_sha256=sha(STUDY/'registration.json'),current_test_read=False))
    print('B109 TRAIN',year,flush=True)


def test(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'test');verify(reg);folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json')
    assert seal['training_sha256']==sha(folder/'training.json')and seal['registration_sha256']==sha(STUDY/'registration.json')and not seal['current_test_read']
    write(folder/'predictions.json.gz',bundle(reg,year));write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)));print('B109 TEST',year,flush=True)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);records={};policies={}
    for year in range(2018,2026):
        folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json');receipt=read(folder/'test-receipt.json')
        assert seal['training_sha256']==sha(folder/'training.json')and receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')
        records[year]=read(folder/'predictions.json.gz');policies[year]=tr['parent_policy']
    values,counts=frame(days,prices,records,policies);bank=load_bank(SOURCE,days,lambda p:bound(reg,p),2025);carry=load_bank(CARRY,days,lambda p:bound(reg,p),2025)
    assert bank['policies']['Y01']==policies and values['scores']['BASE_TREE']==bank['scores']['BASE_TREE']and values['flags']==bank['flags']
    return values,bank,carry


def targets(assembled,recipe):
    values,bank,carry=assembled;n=recipe['id'];days,prices=values['days'],values['prices']
    if recipe['kind']=='LONG_PROFIT'or n in ('P02','PX03','VX04','CT02','ME01','MX03','TS04'):
        target,entry=component(days,prices,values['scores'],{'Y01':values['policies']},values['flags'],values['learner'],.5,'MODEL')
        parent='ME01'if recipe['kind']=='LONG_PROFIT'or n in ('MX03','TS04')else n
        if parent in ('PX03','VX04','CT02','ME01'):target,entry,_=patch_profit_exit(target,entry,PROFIT_ARMS[2])
        if parent in ('VX04','CT02','ME01'):target,entry,_=patch_budget(days,target,entry,values['policies'],None)
        if parent in ('CT02','ME01'):target,entry,_=original_cold_gate(days,prices,values['scores'],values['flags'],values['policies'],target,entry,ORIGINAL_COLD_ARMS[1])
        if parent=='ME01':target,entry,_=original_entry(days,prices,values['scores'],target,entry,ORIGINAL_ENTRY_ARMS[0])
        if n=='MX03':
            target,entry,_=shorter_entry(days,prices,values['scores'],target,entry,SHORT_ENTRY_ARMS[2])
        if n=='TS04'or recipe['kind']=='LONG_PROFIT':
            target,entry,_=parent_trail(values['scores'],target,entry,PARENT_TRAIL_ARMS[0])
        if recipe['kind']=='LONG_PROFIT':return patch_risk(values['scores'],target,entry,recipe['arm'])
        return target,entry,None
    if n=='L06':return (*component(days,prices,bank['scores'],bank['policies'],bank['flags'],values['learner'],.5,'MODEL'),None)
    old=next(r for r in OLD_RECIPES if r['id']==n);banks={'CARRY':carry}if n in ('H04','H05')else{'AVERAGE':bank,'POST':bank}
    return (*old_targets((days,prices,banks,None),old),None)


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard(2025,'replay');verify(reg);assembled=assemble(reg);days,prices=assembled[0]['days'],assembled[0]['prices'];out=[]
    for recipe in RECIPES:
        target,entry,diagnostic=targets(assembled,recipe);ss={};failures={};audits={}
        for case in CASES:
            try:a=run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as e:failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(a,days,prices,target,CASES[case],BORROW[case],{},entry,False)
            if recipe['kind']=='LEGACY':
                base,n=LEGACY[recipe['id']];assert a==bound(reg,base/'accounts'/n/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct']for s in ss.values()),default=None);passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,diagnostic=diagnostic,summaries=ss,failures=failures,audits=audits,goal_gate=passed));print('B109 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,diagnostic,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'));p.add_argument('--year',type=int);a=p.parse_args()
    if a.command in ('train','test'):
        if a.year is None:p.error('--year required')
        globals()[a.command](a.year)
    elif a.command=='run':
        for year in range(2018,2026):
            for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b109',stage,'--year',str(year)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b109','replay'],cwd=ROOT,check=True)
    else:globals()[a.command]()
