"""No-fit same-information and exact shared-state binding checks."""
import sys
sys.dont_write_bytecode=True
import gzip,hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
sys.path.insert(0,str(ROOT))
from lab.price_order_core import GROUPS,ORDERS,ordered,original_coordinates
from lab.tree_factors import predict
SEEDS=[101,307,509,701,907,1103,1701]
def read(p):
 p=Path(p)
 assert p.is_relative_to(ROOT)
 assert not any(s in p.parts for s in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
 if p.suffix=='.gz':
  with gzip.open(p,'rt')as f:return json.load(f)
 return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
studies=ROOT/'studies'
reg=read(studies/'B94-price-column-order-stability/registration.json')
assert reg['orders']==ORDERS and reg['groups']==list(GROUPS)
x=np.sin(np.arange(32*47,dtype=float).reshape(32,47)/11)
permutations=[]
for group in GROUPS:
 p=ORDERS[group]
 assert sorted(p)==list(range(47))
 y=ordered(x,group)
 assert np.array_equal(y[:,np.argsort(p)],x)
 assert y.flags.c_contiguous
 state=read(studies/'B94-price-column-order-stability/folds/2025/models'/f'{group}.json.gz')['members'][0]
 mapped=original_coordinates(state,group)
 err=float(np.max(np.abs(predict(state,y)-predict(mapped,x))))
 assert err<=2e-12
 permutations.append({'group':group,'inverse_recovers_original_exactly':True,
                       'fixed_model_coordinate_mapping_error':err,'feature_count':47})

shared_huber=[]
shared_price=[]
for year in range(2019,2026):
 a=studies/'B67-lag-matched-short-supervision/folds'/str(year)
 b=studies/'B88A-short-net-loss-families/folds'/str(year)
 ta,tb=read(a/'training.json'),read(b/'training.json')
 for head in ('L1','L2'):
  for seed in SEEDS:
   pa=a/'models'/f'{head}-{seed}.json.gz'
   pb=b/'models'/f'HUBER_{head}-{seed}.json.gz'
   digest=sha(pa)
   assert digest==sha(pb)==ta['model_states'][f'models/{head}-{seed}.json.gz']==tb['model_states'][f'models/HUBER_{head}-{seed}.json.gz']
   shared_huber.append({'year':year,'head':head,'seed':seed,'identical_state_sha256':digest})
 p=read(studies/'B81-reported-volume-long-core/folds'/str(year)/'models/PRICE_L7.json.gz')
 q=read(studies/'B94-price-column-order-stability/folds'/str(year)/'models/ORIGINAL.json.gz')
 assert p['members']==q['members'] and p['receipt']==q['receipt']
 shared_price.append({'year':year,'identical_numeric_members':len(p['members']),
                      'receipts_exact':True,'cutoff':p['cutoff']})

analyses={}
for study,keys in (
 ('B94-price-column-order-stability',['qualification','duplicate_groups','unique_four_cost_paths','original_identity_vs_p02']),
 ('B81-reported-volume-long-core',['qualification','duplicate_groups','unique_four_cost_paths','strict_PIT']),
 ('B88A-short-net-loss-families',['qualification','duplicate_groups','unique_four_cost_paths','identity_vs_p02','mechanism'])):
 a=read(studies/study/'analysis.json')
 assert a['validation_read']is False
 analyses[study]={k:a[k]for k in keys}

result={'round':8,'all_checks_pass':True,'no_model_fits':True,
 'information_preserving_orders':permutations,'identical_B67_B88A_HUBER_states':len(shared_huber),
 'identical_B81_B94_ORIGINAL_members':sum(x['identical_numeric_members']for x in shared_price),
 'shared_huber_bindings':shared_huber,'shared_price_bindings':shared_price,
 'registered_counts':{'B81_research_fits':1225,'B81_final_members':245,
                      'B94_research_fits':980,'B94_final_members':196,'B88A_research_fits':392,'B88A_final_members':392},
 'analysis_snapshots':analyses,
 'scope':'列置换逆变换/已定模型坐标映射和现有数字模型同一性；未拟合、挑选seed或改阈值，未估计有效独立市场样本数。'}
with (OUT/'r08_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items()if k not in ('shared_huber_bindings','analysis_snapshots')},ensure_ascii=False))
