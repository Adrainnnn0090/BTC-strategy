"""Fixed ExtraTrees STOP long core with original short-net gate and risk."""
import argparse,subprocess,sys,inspect
from importlib.metadata import version
import numpy as np
from threadpoolctl import threadpool_limits
from sklearn.ensemble import ExtraTreesRegressor
import sklearn.tree._tree as tree_binary
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b81_io import STUDY,SOURCE,LABELS,ORIGINAL,PREPARATION,QUALITY,ANCHOR,LONGLABELS,CARRY,LEGACY,FEATURES,install_guard,load_volume_fold
from .volume_short_factors import append_volume
from .volume_long_core import replace_stop
from .label_trees import tune,infer,PROFILES
from .sgd import matured
from .execution_labels import target_vector
from .tree_stability import SEEDS
from .conditional_short import component
from .full_retained import load_bank
from .b64a import RECIPES as OLD_RECIPES,targets as old_targets
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

GROUPS=[dict(id='PAD47',group='PAD47',lag=7),dict(id='PRICE_L7',group='PRICE47',lag=7),dict(id='VOL_L7',group='VOL47',lag=7),dict(id='PRICE_L30',group='PRICE47',lag=30),dict(id='VOL_L30',group='VOL47',lag=30)]
RECIPES=[dict(id=f'P{i+1:02}',kind='CORE',stream=g['id'])for i,g in enumerate(GROUPS)]+[dict(id=n,kind='LEGACY')for n in LEGACY]
SOURCES=('lab/b81.py','lab/b81_io.py','lab/volume_long_core.py','lab/volume_short_factors.py','lab/volume_walkforward.py',
 'tools/volume_short_reference.py','tools/verify_b81.py','tests/test_b81.py','notes/RESEARCH_2025_SCOPE_AUTHORIZED.md',
 'notes/proposed-reported-volume-long-core.md','studies/B81-reported-volume-long-core/spec.md')


def freeze():
    short=read(LABELS/'registration.json');long=read(LONGLABELS/'registration.json');prep=read(PREPARATION/'preparation-registration.json');carry=read(CARRY/'registration.json')
    proof=read(PREPARATION/'source-verification.json');q=read(QUALITY/'verification.json');lp=read(LONGLABELS/'verification.json')
    assert proof['status']=='PASS_PHYSICAL_REPORTED_VOLUME_SOURCE_ROLES'and proof['files']==16 and proof['projected_records']==16068 and proof['manifest_sha256']==sha(FEATURES/'manifest.json')
    assert q['status']=='PASS_INDEPENDENT_REPORTED_VOLUME_SOURCE_AUDIT'and q['technical_pass_fields']==['volume_reported_spot_usd_1d']and not q['strict_point_in_time_qualified']
    assert lp['status']=='PASS_ACTIVITY_FEATURES_LABELS_FORECASTS_AND_NATIVE_ACCOUNTS'and lp['independently_checked_labels']==10548
    previous=read(PREPARATION/'registration.json');assert previous['groups']==GROUPS
    code={}
    for group in (short['sources'],short['inherited_sources'],long['sources'],prep['sources'],carry['sources']):
        for f,d in group.items():
            if f.startswith('studies/'):continue
            assert f not in code or code[f]==d,f
            code[f]=d
    assert all(sha(ROOT/f)==d for f,d in code.items());runtime=read(ANCHOR/'registration.json')['project_runtime_sources'];assert all(sha(f)==d for f,d in runtime.items())
    binding={}
    for base in (SOURCE,LABELS,ORIGINAL,LONGLABELS,CARRY,ANCHOR,QUALITY,PREPARATION):
        p=base/'registration.json';binding[str(p.relative_to(ROOT))]=sha(p)
    for p in (LABELS/'verification.json',LONGLABELS/'verification.json',CARRY/'verification.json',ANCHOR/'verification.json',ORIGINAL/'verification.json',
        QUALITY/'verification.json',QUALITY/'quality.json',QUALITY/'seal.json',PREPARATION/'preparation-registration.json',PREPARATION/'source-verification.json'):
        binding[str(p.relative_to(ROOT))]=sha(p)
    for year in range(2018,2026):
        for base,names in ((SOURCE,('training.json','seal.json','test-receipt.json','predictions.json.gz')),
            (LABELS,('seal.json','test-receipt.json','predictions.json.gz')),(ORIGINAL,('seal.json','test-receipt.json','predictions.json.gz')),
            (CARRY,('training.json','seal.json','test-receipt.json','predictions.json.gz')),(LONGLABELS,('training.json','seal.json'))):
            for n in names:
                p=base/'folds'/str(year)/n;binding[str(p.relative_to(ROOT))]=sha(p)
        assert read(SOURCE/'folds'/str(year)/'training.json')['y01_policy']==read(LONGLABELS/'folds'/str(year)/'training.json')['y01_policy']
        if year>2018:
            p=LONGLABELS/'folds'/str(year)/'labels/STOP.json.gz';binding[str(p.relative_to(ROOT))]=sha(p)
    for base,n in LEGACY.values():
        for case in CASES:
            p=base/'accounts'/n/f'{case}.json.gz';binding[str(p.relative_to(ROOT))]=sha(p)
    estimator={f:sha(f)for f in (inspect.getfile(ExtraTreesRegressor),tree_binary.__file__)}
    write(STUDY/'registration.json',dict(groups=GROUPS,recipes=RECIPES,profiles=PROFILES,seeds=SEEDS,source=binding,inherited_sources=code,
        sources={f:sha(ROOT/f)for f in SOURCES},versions=short['versions'],project_runtime_sources=runtime,estimator_runtime_sources=estimator,
        manifest_sha256=sha(FOLDS/'manifest.json'),volume_manifest_sha256=sha(FEATURES/'manifest.json'),costs=CASES,financing=BORROW,
        research_member_fits=1225,final_members=245,independent_labels=10548,independent_inner_library_fits=980,
        prescribed_pipeline_rebuilds=5,pipeline_estimator_fits=25,fixed_refit_year=2025,fixed_refit_seed=101,
        accounts=48,exact_controls=28,prescribed_replay=['P05','DELAY'],feature_tolerance=2e-12,score_tolerance=2e-12,inner_loss_tolerance=2e-12,
        target_return_pct=10000,strict_drawdown_pct=35,strict_PIT=False,validation_read=False,
        qualification='conditional reportedUSDvolume longSTOP task;fixed original short gate/risk;consumed2018–2025;all2026excluded'))
    print('B81 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['groups']==GROUPS and reg['recipes']==RECIPES and reg['profiles']==PROFILES and reg['seeds']==list(SEEDS)and len(RECIPES)==12
    assert sha(FOLDS/'manifest.json')==reg['manifest_sha256']and sha(FEATURES/'manifest.json')==reg['volume_manifest_sha256']
    assert reg['costs']=={k:list(v)for k,v in CASES.items()}and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for f,d in {**reg['project_runtime_sources'],**reg['estimator_runtime_sources']}.items():assert sha(f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def features(days,prices,volumes):
    return {g['id']:append_volume(days,prices,volumes if g['group']=='VOL47'else None,g['lag'],g['group'])for g in GROUPS}


def train(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'train');verify(reg);folder=STUDY/'folds'/str(year)
    parent=bound(reg,SOURCE/'folds'/str(year)/'training.json');ps=bound(reg,SOURCE/'folds'/str(year)/'seal.json')
    long=bound(reg,LONGLABELS/'folds'/str(year)/'training.json');ls=bound(reg,LONGLABELS/'folds'/str(year)/'seal.json')
    assert parent['cutoff']==ps['cutoff']==long['cutoff']==ls['cutoff']==f'{year-1}-12-31'and not ps['current_test_read']and not ls['current_test_read']
    assert ps['training_sha256']==sha(SOURCE/'folds'/str(year)/'training.json')and ls['training_sha256']==sha(LONGLABELS/'folds'/str(year)/'training.json')
    assert parent['y01_policy']==long['y01_policy'];days,prices=load_fold(year);cut=len(days)-1;models={};fits=0;labelsha=None;volumehash=None
    try:ids=matured(cut,60);matured(int(ids[-120:-60][0]),60)
    except (ValueError,IndexError):
        assert year==2018;ids=np.asarray([],dtype=int)
    if len(ids):
        p=LONGLABELS/'folds'/str(year)/'labels/STOP.json.gz';bank=bound(reg,p);labelsha=sha(p);assert ls['label_sha256']['STOP']==labelsha
        assert [r['index']for r in bank]==ids.tolist();vector=target_vector(bank,len(days))
        rows=features(days,prices,load_volume_fold(year,days,'train'));volumehash=sha(FEATURES/str(year)/'train.json.gz')
        for group in GROUPS:
            with threadpool_limits(limits=1):members,receipt=tune(rows[group['id']],vector,cut,'STOP')
            p=folder/'models'/f'{group["id"]}.json.gz';write(p,dict(feature_spec=group,members=members,receipt=receipt,cutoff=days[-1],source_label_sha256=labelsha))
            models[str(p.relative_to(folder))]=sha(p);fits+=receipt['model_fits'];print('B81 MODEL',year,group['id'],fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,model_states=models,y01_policy=parent['y01_policy'],
        source_label_sha256=labelsha,volume_train_sha256=volumehash,inner_profile_selections=len(GROUPS)*7 if len(ids)else 0,risk_search_calls=0,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(cutoff=days[-1],training_sha256=sha(folder/'training.json'),train_sha256=sha(FOLDS/str(year)/'train.json'),
        registration_sha256=sha(STUDY/'registration.json'),current_test_read=False))
    print('B81 TRAIN',year,fits,flush=True)


def test(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'test');verify(reg);folder=STUDY/'folds'/str(year)
    tr=read(folder/'training.json');seal=read(folder/'seal.json');assert seal['training_sha256']==sha(folder/'training.json')and seal['registration_sha256']==sha(STUDY/'registration.json')
    days,prices=load_fold(year,include_test=True);first=days.index(f'{year-1}-12-31');last=days.index(f'{year}-12-31')
    original=bound(reg,SOURCE/'folds'/str(year)/'predictions.json.gz');assert original['dates']==days[first:last];scores={};vhashes=None
    if tr['model_fits']:
        rows=features(days,prices,load_volume_fold(year,days,'test'));vhashes={r:sha(FEATURES/str(year)/f'{r}.json.gz')for r in ('train','test')}
    for group in GROUPS:
        key=group['id'];p=folder/'models'/f'{key}.json.gz'
        if not tr['model_fits']:scores[key]=[None]*(last-first)
        else:
            assert sha(p)==tr['model_states'][str(p.relative_to(folder))];m=read(p);assert m['source_label_sha256']==tr['source_label_sha256']
            scores[key]=infer(m['members'],rows[key][first:last]).tolist()
        assert [v is None for v in scores[key]]==[v is None for v in original['scores']['CAL44_STOP']]
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores))
    write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),
        test_sha256=sha(FOLDS/str(year)/'test.json'),volume_sha256=vhashes,fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)))
    print('B81 TEST',year,flush=True)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)};bank=load_bank(SOURCE,days,lambda p:bound(reg,p),2025);carry=load_bank(CARRY,days,lambda p:bound(reg,p),2025)
    scores={k:[None]*len(days)for k in [g['id']for g in GROUPS]+['B67','B66']}
    for year in range(2018,2026):
        folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json');receipt=read(folder/'test-receipt.json');forecast=read(folder/'predictions.json.gz')
        assert seal['training_sha256']==sha(folder/'training.json')and receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')
        assert tr['y01_policy']==bank['policies']['Y01'][year];streams=dict(forecast['scores'])
        for base,key,stream in ((LABELS,'B67','MEAN'),(ORIGINAL,'B66','ALL_D2_HUBER')):
            old=bound(reg,base/'folds'/str(year)/'predictions.json.gz');os=bound(reg,base/'folds'/str(year)/'seal.json');rr=bound(reg,base/'folds'/str(year)/'test-receipt.json')
            assert rr['seal_sha256']==sha(base/'folds'/str(year)/'seal.json')and rr['predictions_sha256']==sha(base/'folds'/str(year)/'predictions.json.gz')and os['registration_sha256']==sha(base/'registration.json')
            assert old['dates']==forecast['dates'];streams[key]=old['scores'][stream]
        for key,values in streams.items():
            for day,v in zip(forecast['dates'],values,strict=True):scores[key][where[day]]=v
    for g in GROUPS:replace_stop(bank['scores'],scores[g['id']])
    return days,prices,bank,scores,carry


def targets(values,recipe):
    days,prices,bank,scores,carry=values;n=recipe['id']
    if recipe['kind']=='CORE':return component(days,prices,replace_stop(bank['scores'],scores[recipe['stream']]),bank['policies'],bank['flags'],scores['B67'],.5,'MODEL')
    if n in ('H04','H05','T12','Y01'):
        old=next(r for r in OLD_RECIPES if r['id']==n);banks={'CARRY':carry}if n in ('H04','H05')else{'AVERAGE':bank,'POST':bank}
        return old_targets((days,prices,banks,None),old)
    return component(days,prices,bank['scores'],bank['policies'],bank['flags'],scores['B66'if n=='Q05'else'B67'],.25 if n=='L05'else.5,'MODEL')


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard(2025,'replay');verify(reg);values=assemble(reg);days,prices=values[:2];out=[]
    for recipe in RECIPES:
        target,allowed=targets(values,recipe);ss={};audits={};failures={}
        for case in CASES:
            try:a=run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=allowed,annual_settlement=False)
            except ValueError as e:failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(a,days,prices,target,CASES[case],BORROW[case],{},allowed,False)
            if recipe['kind']=='LEGACY':
                base,name=LEGACY[recipe['id']];assert a==bound(reg,base/'accounts'/name/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct']for s in ss.values()),default=None);passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,summaries=ss,audits=audits,failures=failures,goal_gate=passed));print('B81 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'));p.add_argument('--year',type=int);a=p.parse_args()
    if a.command in ('train','test'):
        if a.year is None:p.error('--year required')
        globals()[a.command](a.year)
    elif a.command=='run':
        for year in range(2018,2026):
            for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b81',stage,'--year',str(year)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b81','replay'],cwd=ROOT,check=True)
    else:globals()[a.command]()
