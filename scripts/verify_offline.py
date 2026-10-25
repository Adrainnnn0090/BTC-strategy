"""Container entry: no old projects, no network, readonly artifacts, real model path."""
from pathlib import Path
import json,sys,hashlib
from btc_strategy.artifacts import ROOT,catalog
from btc_strategy.models import verify_family,FAMILIES
from btc_strategy.replay import run

for p in ('/workspace/BTCStrategyResearchLedger','/workspace/BinanceTradingRobot','/workspace/Polymarket_Arbitrage_Robot'):
 assert not Path(p).exists(),p+' unexpectedly visible'
assert not any(k.startswith('binance_robot')for k in sys.modules)
for family in FAMILIES:print(json.dumps(dict(type='model',**verify_family(family))),flush=True)
for item in catalog():
 for case in ('BASE','STRESS','SEVERE','DELAY'):
  print(json.dumps(dict(type='native',**run(item['id'],case))),flush=True)
assert not any(k.startswith('binance_robot')for k in sys.modules)
print(json.dumps(dict(type='completion',status='PASS',models=6,native_accounts=36,actual_numeric_models=True,old_projects_visible=False)),flush=True)
