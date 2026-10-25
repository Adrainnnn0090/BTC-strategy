from datetime import date,timedelta
from copy import deepcopy
import pytest
from btc_strategy.artifacts import resolve_artifact
from btc_strategy.models import annual_states,feature_matrix,reconstruct
from btc_strategy.training import refit,training_read_allowed
from btc_strategy.validation import development_market

def market(n=500):return dict(days=[(date(2017,1,1)+timedelta(days=i)).isoformat()for i in range(n)],prices=[100.+i*.1 for i in range(n)])

@pytest.mark.parametrize('path',['models/base_tree/2026/model.json.gz','artifacts/V01/rows.json','artifacts/v01-unsafe/rows.json','artifacts/V01.json','artifacts/v02_unsafe.json','training_inputs/2026/base_tree.json.gz','provenance/studies/X/2026/training.json','../BTCStrategyResearchLedger/data/rows.json'])
def test_forbidden_paths_fail_before_open(path,monkeypatch):
 from pathlib import Path
 monkeypatch.setattr(Path,'read_bytes',lambda self:(_ for _ in ()).throw(AssertionError('must reject before opening')))
 with pytest.raises(ValueError):resolve_artifact(path)

@pytest.mark.parametrize('year',[2026,2017,2025.0,True])
def test_unregistered_fold_cannot_load_or_fit(year):
 with pytest.raises(ValueError):annual_states('base_tree',year)
 with pytest.raises(ValueError):refit('base_tree',year)

@pytest.mark.parametrize('kind',['unknown','bad'])
def test_unknown_feature_family_rejected(kind):
 with pytest.raises(ValueError):feature_matrix(kind,market())

@pytest.mark.parametrize('change',['middle2026','duplicate','outoforder','nan','negative'])
def test_invalid_economic_input_rejected(change):
 m=market()
 if change=='middle2026':m['days'][250]='2026-01-01'
 elif change=='duplicate':m['days'][250]=m['days'][249]
 elif change=='outoforder':m['days'][250],m['days'][251]=m['days'][251],m['days'][250]
 elif change=='nan':m['prices'][250]=float('nan')
 else:m['prices'][250]=-1.
 with pytest.raises(ValueError):feature_matrix('base_tree',m)


def test_price_only_features_need_no_mining_and_are_prefix_causal():
 m=market();a=feature_matrix('price47',m);changed=deepcopy(m);changed['prices'][400:]=[100000.]*100
 assert(a[:400]==feature_matrix('price47',changed)[:400]).all()
 short={k:v[:400]for k,v in m.items()};assert(a[:400]==feature_matrix('price47',short)).all()


def test_training_role_denies_context_and_other_folds():
 from btc_strategy.artifacts import ROOT
 assert training_read_allowed(ROOT/'training_inputs/2025/price47.json.gz','price47',2025)
 for path in ['artifacts/contexts/high_return.json.gz','artifacts/accounts/LP35/STRESS.json.gz','training_inputs/2024/price47.json.gz','training_inputs/2025/short_huber.json.gz','models/base_tree/2025/x.json.gz']:
  assert not training_read_allowed(ROOT/path,'price47',2025)


def test_missing_2018_remains_missing():
 assert annual_states('base_tree',2018)==[]
 values=reconstruct('base_tree',market(365))
 assert all(v is None for v in values)


def test_manifest_cannot_resurrect_2018_before_reading_model(monkeypatch):
 from btc_strategy import models
 monkeypatch.setattr(models,'read',lambda _:[dict(family='base_tree',fold_year=2018,missing=False,files=[dict(path='synthetic')])])
 monkeypatch.setattr(models,'read_verified',lambda *a:(_ for _ in ()).throw(AssertionError('must not open fabricated 2018 model')))
 with pytest.raises(ValueError,match='2018'):models.annual_states('base_tree',2018)


@pytest.mark.parametrize('fault',['family','duplicate_date','fold_type','cut_index','embargo','missing'])
def test_training_plan_rejects_broken_identity_and_clock(fault):
 from btc_strategy.training import validate_training_plan
 days=market(365)['days'];p=dict(family='price47',fold_year=2018,dates=days,cutoff='2017-12-31',cut_index=364,embargo=6,model_missing=True)
 validate_training_plan(p,'price47',2018)
 if fault=='family':p['family']='stop44'
 elif fault=='duplicate_date':p['dates'][100]=p['dates'][99]
 elif fault=='fold_type':p['fold_year']=2018.0
 elif fault=='cut_index':p['cut_index']=363
 elif fault=='embargo':p['embargo']=0
 else:p['model_missing']=False
 with pytest.raises(ValueError):validate_training_plan(p,'price47',2018)


@pytest.mark.parametrize('case',['UNKNOWN_CASE',[],None])
def test_bad_replay_case_rejected_before_targets_or_features(case,monkeypatch):
 from btc_strategy import replay
 monkeypatch.setattr(replay,'verify_targets',lambda *a:(_ for _ in ()).throw(AssertionError('must reject before targets')))
 with pytest.raises(ValueError,match='cost case'):replay.run('LP35',case)
