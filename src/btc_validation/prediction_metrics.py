"""Outcomes only; no estimation. Labels must mature entirely within the window."""
import numpy as np
from btc_strategy._frozen.lab import execution_labels,lagged_short
from btc_strategy._runtime.sgd import labels

def measure(family,days,prices,score,start,baseline):
 first=days.index(start);last=len(days)-1;span=62 if family.startswith('short_')else 61;xx=[];yy=[];used=[]
 for i in range(first-1,last-span+1):
  if score[i]is None:continue
  if family in('base_tree','mining58'):truth=float(labels(prices,np.asarray([i]),60)[0])
  elif family in('stop44','price47'):truth=execution_labels.path_label(days,prices,i,'STOP')['log_return']
  else:
   a=lagged_short.label(days,prices,i,1);b=lagged_short.label(days,prices,i,2)
   if a['status']!='DEFINED'or b['status']!='DEFINED':continue
   truth=(a['simple_return']+b['simple_return'])/2
  if i+span>last or days[i+1]<start:raise AssertionError('validation outcome crossed window')
  xx.append(score[i]);yy.append(truth);used.append(i)
 if not used:return dict(family=family,status='NO_MATURE_OUTCOMES',samples=0)
 x=np.asarray(xx);y=np.asarray(yy);mse=float(np.mean((x-y)**2));mae=float(np.mean(abs(x-y)));null_mse=float(np.mean((baseline['mean']-y)**2));null_mae=float(np.mean(abs(baseline['median']-y)))
 return dict(family=family,status='COMPLETE',samples=len(y),first_decision=days[used[0]],last_decision=days[used[-1]],last_outcome=days[used[-1]+span],
  mse=mse,mae=mae,training_mean_null_mse=null_mse,training_median_null_mae=null_mae,mse_skill=1-mse/null_mse if null_mse else None,
  sign_accuracy=float(np.mean((x>0)==(y>0))),mean_prediction=float(x.mean()),mean_outcome=float(y.mean()),
  qualification='60-day overlapping outcomes, with 61/62 endpoint; descriptive dependent observations, not iid trials or calibrated probabilities.')
