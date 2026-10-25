"""Fixed old ETHfactor recipe transferred to short-net; strongest longcore fixed."""
import argparse,inspect,subprocess,sys
from importlib.metadata import version
import numpy as np
from threadpoolctl import threadpool_limits
from sklearn.ensemble import GradientBoostingRegressor
import sklearn.tree._tree as tree_binary
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b86_io import STUDY,PARENT,SOURCE,LABELS,CARRY,ANCHOR,LEGACY,QUALITY,install_guard
from .eth_role_parity import FEATURES,load_eth
from .eth_short_transfer import GROUPS,features
from .lagged_short import HEADS,LOSS,target_vector,fit
from .boosted_stop import PROFILE
from .tree_stability import SEEDS
from .tree_factors import predict
from .b82 import bundle
from .price_trail_activation import frame
from .full_retained import load_bank
from .conditional_short import component
from .b64a import RECIPES as OLD_RECIPES,targets as old_targets
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

MODELS=[dict(id=g+'_'+h['id'],group=g,head=h)for g in GROUPS for h in HEADS]
RECIPES=[dict(id=f'E{i+1:02}',kind='MODEL',stream=g)for i,g in enumerate(GROUPS)]+[dict(id=n,kind='LEGACY')for n in LEGACY]
SOURCES=('lab/b86.py','lab/b86_io.py','lab/eth_short_transfer.py','lab/eth_factors.py','lab/eth_role_parity.py','lab/b82.py','lab/b82_io.py','lab/price_trail_activation.py',
 'tools/eth_transfer_reference.py','tools/verify_b86.py','tests/test_b86.py','notes/proposed-eth-short-net-transfer.md','studies/B86-eth-short-net-transfer/spec.md')


def freeze():
    p=read(PARENT/'registration.json');v=read(PARENT/'verification.json');proof=read(STUDY/'source-verification.json');prep=read(STUDY/'preparation-registration.json')
    assert v['status']=='PASS'and not v['validation_read']and proof['status']=='PASS_EXISTING_ETH_PHYSICAL_SOURCE_PARITY'and proof['files']==16 and proof['projected_records']==16068 and not proof['strict_PIT']
    assert proof['manifest_sha256']==prep['manifest_sha256']==sha(FEATURES/'manifest.json')and not proof['validation_read']
    code={f:d for f,d in {**p['sources'],**p['inherited_sources'],**prep['sources']}.items()if not f.startswith('studies/')};assert all(sha(ROOT/f)==d for f,d in code.items())
    runtime=p['project_runtime_sources'];assert all(sha(f)==d for f,d in runtime.items());binding={}
    for base in (PARENT,SOURCE,LABELS,CARRY,ANCHOR,QUALITY):
        q=base/'registration.json';binding[str(q.relative_to(ROOT))]=sha(q)
    for q in [*(b/'verification.json'for b in (PARENT,LABELS,CARRY,ANCHOR)),QUALITY/'quality.json',QUALITY/'decision.json',*(STUDY/n for n in ('preparation-registration.json','preparation-spec.md','source-verification.json','source-checks.json','source-seal.json'))]:binding[str(q.relative_to(ROOT))]=sha(q)
    for year in range(2018,2026):
        for base in (PARENT,SOURCE,LABELS,CARRY):
            for n in ('training.json','seal.json','predictions.json.gz','test-receipt.json'):
                q=base/'folds'/str(year)/n;binding[str(q.relative_to(ROOT))]=sha(q)
        if year>2018:
            q=LABELS/'folds'/str(year)/'labels.json.gz';binding[str(q.relative_to(ROOT))]=sha(q)
    for base,n in LEGACY.values():
        for case in CASES:
            q=base/'accounts'/n/f'{case}.json.gz';binding[str(q.relative_to(ROOT))]=sha(q)
    estimator={f:sha(f)for f in (inspect.getfile(GradientBoostingRegressor),tree_binary.__file__)}
    write(STUDY/'registration.json',dict(groups=GROUPS,models=MODELS,recipes=RECIPES,heads=HEADS,loss=LOSS,profile=PROFILE,seeds=SEEDS,
        source=binding,inherited_sources=code,sources={f:sha(ROOT/f)for f in SOURCES},versions=p['versions'],project_runtime_sources=runtime,estimator_runtime_sources=estimator,
        manifest_sha256=sha(FOLDS/'manifest.json'),eth_manifest_sha256=sha(FEATURES/'manifest.json'),costs=CASES,financing=BORROW,
        model_fits=294,final_members=294,independent_labels=21082,prescribed_refits=6,fixed_refit_year=2025,fixed_refit_seed=101,
        accounts=36,exact_controls=24,prescribed_replay=['E03','DELAY'],feature_tolerance=2e-12,score_tolerance=2e-12,label_tolerance=2e-12,money_label_tolerance=1e-10,
        target_return_pct=10000,strict_drawdown_pct=35,strict_PIT=False,validation_read=False,
        qualification='conditional late-vintage ETH54lag7 in matchedshortnet;fixed P02long/risk;CCBY-NClocal;consumed2018–2025;all2026excluded'))
    print('B86 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['groups']==list(GROUPS)and reg['models']==MODELS and reg['recipes']==RECIPES and reg['heads']==HEADS and reg['loss']==LOSS and reg['profile']==PROFILE and reg['seeds']==list(SEEDS)and len(RECIPES)==9
    assert sha(FOLDS/'manifest.json')==reg['manifest_sha256']and sha(FEATURES/'manifest.json')==reg['eth_manifest_sha256']and reg['costs']=={k:list(v)for k,v in CASES.items()}and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for f,d in {**reg['project_runtime_sources'],**reg['estimator_runtime_sources']}.items():assert sha(f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def train(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'train');verify(reg);folder=STUDY/'folds'/str(year)
    old=bound(reg,SOURCE/'folds'/str(year)/'training.json');os=bound(reg,SOURCE/'folds'/str(year)/'seal.json');parent=bound(reg,LABELS/'folds'/str(year)/'training.json');ps=bound(reg,LABELS/'folds'/str(year)/'seal.json')
    assert old['cutoff']==os['cutoff']==parent['cutoff']==ps['cutoff']==f'{year-1}-12-31'and not ps['current_test_read']and not os['current_test_read']and ps['training_sha256']==sha(LABELS/'folds'/str(year)/'training.json')and old['y01_policy']==parent['y01_policy']
    days,prices=load_fold(year);cut=len(days)-1;ids=np.asarray(parent['common_ids'],dtype=int);states={};receipts={m['id']:[]for m in MODELS};fitted=0;ethsha=labelsha=None
    if len(ids)>=128:
        assert year>2018;banks=bound(reg,LABELS/'folds'/str(year)/'labels.json.gz');labelsha=sha(LABELS/'folds'/str(year)/'labels.json.gz');assert labelsha==parent['labels_sha256']
        eth=load_eth(year,days,'train',reg['eth_manifest_sha256']);rows=features(days,prices,eth);ethsha=sha(FEATURES/str(year)/'train.json.gz')
        for model in MODELS:
            key=model['id'];vector=target_vector(banks[model['head']['id']],len(days))
            for seed in SEEDS:
                with threadpool_limits(limits=1):state,rec=fit(rows[model['group']],vector,ids,cut,model['head'],seed)
                state={**state,'feature_group':model['group']};p=folder/'models'/f'{key}-{seed}.json.gz';write(p,state);states[str(p.relative_to(folder))]=sha(p);receipts[key].append(rec);fitted+=1
            print('B86 MODEL',year,key,fitted,flush=True)
    else:assert year==2018 and len(ids)==0
    write(folder/'training.json',dict(year=year,cutoff=days[-1],fits=fitted,selection_calls=0,y01_policy=old['y01_policy'],model_states=states,receipts=receipts,
        common_ids=ids.tolist(),source_labels_sha256=labelsha,eth_train_sha256=ethsha,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(training_sha256=sha(folder/'training.json'),train_sha256=sha(FOLDS/str(year)/'train.json'),cutoff=days[-1],current_test_read=False,registration_sha256=sha(STUDY/'registration.json')));print('B86 TRAIN',year,fitted,flush=True)


def test(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'test');verify(reg);folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json')
    assert seal['training_sha256']==sha(folder/'training.json')and seal['registration_sha256']==sha(STUDY/'registration.json')and not seal['current_test_read']
    fixed=bundle(reg,year);days,prices=load_fold(year,include_test=True);first=days.index(f'{year-1}-12-31');last=days.index(f'{year}-12-31');assert fixed['dates']==days[first:last]
    scores={};ethshas=None
    if tr['fits']:
        eth=load_eth(year,days,'test',reg['eth_manifest_sha256']);rows=features(days,prices,eth);ethshas={r:sha(FEATURES/str(year)/f'{r}.json.gz')for r in ('train','test')}
    for model in MODELS:
        key=model['id'];pred=[]
        if not tr['receipts'][key]:scores[key]=[None]*(last-first);continue
        for seed in SEEDS:
            p=folder/'models'/f'{key}-{seed}.json.gz';assert sha(p)==tr['model_states'][str(p.relative_to(folder))];state=read(p);assert state['feature_group']==model['group'];pred.append(predict(state,rows[model['group']][first:last]))
        scores[key]=np.mean(pred,axis=0).tolist()
    for g in GROUPS:
        scores[g]=[None if a is None or b is None else(a+b)/2 for a,b in zip(scores[g+'_L1'],scores[g+'_L2'],strict=True)]
        assert [v is None for v in scores[g]]==[v is None for v in fixed['learner']]
    write(folder/'predictions.json.gz',dict(dates=fixed['dates'],scores=scores,fixed=fixed));write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),
        test_sha256=sha(FOLDS/str(year)/'test.json'),eth_sha256=ethshas,fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)));print('B86 TEST',year,flush=True)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)};records={};policies={};scores={g:[None]*len(days)for g in GROUPS}
    for year in range(2018,2026):
        folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json');receipt=read(folder/'test-receipt.json');f=read(folder/'predictions.json.gz')
        assert seal['training_sha256']==sha(folder/'training.json')and receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')and not receipt['validation_read']
        records[year]=f['fixed'];policies[year]=tr['y01_policy']
        for g in GROUPS:
            for d,v in zip(f['dates'],f['scores'][g],strict=True):scores[g][where[d]]=v
    values,counts=frame(days,prices,records,policies);bank=load_bank(SOURCE,days,lambda p:bound(reg,p),2025);carry=load_bank(CARRY,days,lambda p:bound(reg,p),2025)
    assert bank['policies']['Y01']==policies and values['scores']['BASE_TREE']==bank['scores']['BASE_TREE']and values['flags']==bank['flags']
    return values,bank,carry,scores


def targets(assembled,recipe):
    values,bank,carry,scores=assembled;n=recipe['id'];days,prices=values['days'],values['prices']
    if recipe['kind']=='MODEL'or n=='P02':return component(days,prices,values['scores'],{'Y01':values['policies']},values['flags'],scores[recipe['stream']]if recipe['kind']=='MODEL'else values['learner'],.5,'MODEL')
    if n=='L06':return component(days,prices,bank['scores'],bank['policies'],bank['flags'],values['learner'],.5,'MODEL')
    old=next(r for r in OLD_RECIPES if r['id']==n);banks={'CARRY':carry}if n in ('H04','H05')else{'AVERAGE':bank,'POST':bank}
    return old_targets((days,prices,banks,None),old)


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard(2025,'replay');verify(reg);assembled=assemble(reg);days,prices=assembled[0]['days'],assembled[0]['prices'];out=[]
    for recipe in RECIPES:
        target,entry=targets(assembled,recipe);ss={};failures={};audits={}
        for case in CASES:
            try:a=run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as e:failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(a,days,prices,target,CASES[case],BORROW[case],{},entry,False)
            if recipe['kind']=='LEGACY':
                base,n=LEGACY[recipe['id']];assert a==bound(reg,base/'accounts'/n/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct']for s in ss.values()),default=None);passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,summaries=ss,failures=failures,audits=audits,goal_gate=passed));print('B86 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'));p.add_argument('--year',type=int);a=p.parse_args()
    if a.command in ('train','test'):
        if a.year is None:p.error('--year required')
        globals()[a.command](a.year)
    elif a.command=='run':
        for year in range(2018,2026):
            for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b86',stage,'--year',str(year)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b86','replay'],cwd=ROOT,check=True)
    else:globals()[a.command]()
