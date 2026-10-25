from copy import deepcopy
import hashlib,json,gzip
import pytest
from btc_strategy import models
from btc_strategy.artifacts import ROOT,read,catalog,read_verified
from btc_strategy.strategies import verify_targets


def test_all_selected_rules_match_full_frozen_targets():
 for row in catalog():assert verify_targets(row['id'])['targets_exact']


def test_model_hash_fails_before_deserializing(tmp_path,monkeypatch):
 import btc_strategy.artifacts as a
 monkeypatch.setattr(a,'ROOT',tmp_path)
 p=tmp_path/'models/x.json';p.parent.mkdir();p.write_bytes(b'not valid json')
 with pytest.raises(ValueError,match='hash mismatch'):a.read_verified('models/x.json','0'*64)


def test_short_member_roster_rejects_missing_or_duplicate(monkeypatch):
 manifest=read('models/manifest.json');row=next(x for x in manifest if x['family']=='short_huber'and x['fold_year']==2025)
 monkeypatch.setattr(models,'read',lambda _:manifest)
 original=models.read_verified
 def duplicate(path,digest):
  x=original(path,digest)
  if x['seed']==307:x={**x,'seed':101}
  return x
 monkeypatch.setattr(models,'read_verified',duplicate)
 with pytest.raises(ValueError,match='roster'):models.annual_states('short_huber',2025)


def test_manifest_cannot_route_wrong_year(monkeypatch):
 manifest=deepcopy(read('models/manifest.json'));row=next(x for x in manifest if x['family']=='price47'and x['fold_year']==2025)
 row['files'][0]['path']=row['files'][0]['path'].replace('/2025/','/2024/')
 monkeypatch.setattr(models,'read',lambda _:manifest)
 with pytest.raises(ValueError,match='year/family'):models.annual_states('price47',2025)


def test_real_model_reconstruction_parity():
 for family in models.FAMILIES:assert models.verify_family(family)['max_error']<=2e-12
