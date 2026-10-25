"""Round 06 strict adapter equivalence, pure quotes/metadata; no accounts."""
import ast
import copy
import difflib
import hashlib
import json
import sys
from datetime import datetime,timezone
from decimal import Decimal,ROUND_DOWN,ROUND_UP
from pathlib import Path

SOURCE=Path('/workspace/BTCStrategyResearchLedger')
DELIVERY=Path('/workspace/BTC-strategy')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')

def read_text(path):
    path=Path(path)
    if any(token in str(path).lower() for token in ('2026','v01','v02')):
        raise ValueError('forbidden source path')
    return path.read_text()

def sha_text(value):
    return hashlib.sha256(value.encode()).hexdigest()

def dump(node):
    return ast.dump(node,include_attributes=False)

def function(tree,name):
    return next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name)

def literal_assignment(tree,name):
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id==name for target in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)

source=read_text(SOURCE/'lab/carry_native.py')
delivery=read_text(DELIVERY/'src/btc_strategy/execution.py')
replacements={
    'from binance_robot.execution import INSTRUMENT,VENUE':'from .instrument import INSTRUMENT,VENUE',
    'from binance_robot.runner import paper_instrument':'from .instrument import paper_instrument',
    'from .native import CASES,quote_prices':'from .costs import CASES,quote_prices',
}
expected=source
for old,new in replacements.items():
    assert expected.count(old)==1
    expected=expected.replace(old,new)
source_tree=ast.parse(source)
delivery_tree=ast.parse(delivery)
expected_tree=ast.parse(expected)
execution_checks={
    'exact_text_after_only_three_allowed_import_replacements':delivery==expected,
    'entire_ast_after_only_three_allowed_import_replacements':dump(delivery_tree)==dump(expected_tree),
    'all_top_level_function_asts_unchanged':all(dump(function(source_tree,node.name))==dump(node) for node in delivery_tree.body if isinstance(node,ast.FunctionDef)),
    'MarginResearch_class_ast_unchanged':dump(next(node for node in source_tree.body if isinstance(node,ast.ClassDef)))==dump(next(node for node in delivery_tree.body if isinstance(node,ast.ClassDef))),
}
native_tree=ast.parse(read_text(SOURCE/'lab/native.py'))
costs_tree=ast.parse(read_text(DELIVERY/'src/btc_strategy/costs.py'))
cost_checks={
    'CASES_exact':literal_assignment(native_tree,'CASES')==literal_assignment(costs_tree,'CASES'),
    'BORROW_exact':literal_assignment(source_tree,'BORROW')==literal_assignment(costs_tree,'BORROW'),
    'quote_prices_function_ast_exact':dump(function(native_tree,'quote_prices'))==dump(function(costs_tree,'quote_prices')),
}
runner_path=Path('/workspace/BinanceTradingRobot/backend/.venv/lib/python3.12/site-packages/binance_robot/runner.py')
runner_tree=ast.parse(read_text(runner_path))
instrument_tree=ast.parse(read_text(DELIVERY/'src/btc_strategy/instrument.py'))
instrument_function_exact=dump(function(runner_tree,'paper_instrument'))==dump(function(instrument_tree,'paper_instrument'))

sys.path.insert(0,str(DELIVERY/'src'))
from btc_strategy import costs,instrument
quote_namespace={'Decimal':Decimal,'ROUND_DOWN':ROUND_DOWN,'ROUND_UP':ROUND_UP}
quote_module=ast.Module(body=[copy.deepcopy(function(native_tree,'quote_prices'))],type_ignores=[])
exec(compile(ast.fix_missing_locations(quote_module),'<isolated-original-quote-prices>','exec'),quote_namespace)
prices=('5','5.00001','5.00999','99.99999','100','100.005','100.009999','30000.123456','99999.995','1000000.000001','0.010001','0.019999')
slips=sorted({case[1] for case in costs.CASES.values()}|{0.,.000001})
quote_cases=[{'price':price,'slip':slip,'equal':quote_namespace['quote_prices'](price,slip)==costs.quote_prices(price,slip)} for price in prices for slip in slips]
instrument_namespace={name:getattr(instrument,name) for name in ('INSTRUMENT','VENUE','CurrencyPair','Symbol','Currency','Price','Quantity','Money')}
instrument_namespace['Decimal']=Decimal
instrument_module=ast.Module(body=[copy.deepcopy(function(runner_tree,'paper_instrument'))],type_ignores=[])
exec(compile(ast.fix_missing_locations(instrument_module),'<isolated-original-paper-instrument>','exec'),instrument_namespace)
timestamps=[0,int(datetime(2018,1,1,tzinfo=timezone.utc).timestamp())*10**9,int(datetime(2025,12,31,tzinfo=timezone.utc).timestamp())*10**9]
instrument_cases=[{'timestamp_ns':ts,'dictionary_exact':instrument.CurrencyPair.to_dict(instrument_namespace['paper_instrument'](ts))==instrument.CurrencyPair.to_dict(instrument.paper_instrument(ts))} for ts in timestamps]

runtime=[]
for file in sorted((DELIVERY/'src/btc_strategy/_runtime').glob('*.py')):
    if file.name in ('__init__.py','clock.py'):
        continue
    original=read_text(SOURCE/'lab'/file.name)
    current=read_text(file)
    exact=current==original
    expected_current=original.replace('from .b05 import forecast_year','from .clock import forecast_year') if file.name=='bear_short_overlay.py' else original
    tree=ast.parse(current)
    forbidden_imports=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module and (node.module.startswith('binance_robot') or node.module=='b05')]
    runtime.append({'file':file.name,'bytes_exact_to_source':exact,'only_allowed_clock_import_change':current==expected_current,'forbidden_trading_or_driver_imports':forbidden_imports})
original_clock=function(ast.parse(read_text(SOURCE/'lab/b05.py')),'forecast_year')
new_clock=function(ast.parse(read_text(DELIVERY/'src/btc_strategy/_runtime/clock.py')),'forecast_year')
result={'round':6,'source_carry_native_sha256':sha_text(source),'delivery_execution_sha256':sha_text(delivery),
    'allowed_import_replacements':replacements,'execution_checks':execution_checks,
    'execution_text_diff':''.join(difflib.unified_diff(source.splitlines(True),delivery.splitlines(True),fromfile='source/carry_native.py',tofile='delivery/execution.py')),
    'cost_checks':cost_checks,'quote_case_count':len(quote_cases),'all_quote_cases_exact':all(row['equal'] for row in quote_cases),'quote_cases':quote_cases,
    'instrument_function_ast_exact':instrument_function_exact,'instrument_pure_metadata_cases':instrument_cases,
    'runtime_original_module_count':len(runtime),'runtime_source_checks':runtime,
    'runtime_all_only_allowed_change':all(row['only_allowed_clock_import_change'] and not row['forbidden_trading_or_driver_imports'] for row in runtime),
    'clock_function_ast_exact':dump(original_clock)==dump(new_clock),
    'native_replay_initial_receipt_read':False,'native_account_replayed':False,
    'original_runner_imported':False,'pure_quote_and_metadata_functions_only':True,
    'r05_import_failure_retested_or_overwritten':False,'source_or_delivery_written':False}
with (OWN/'checks-r06.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(json.dumps({key:result[key] for key in ('execution_checks','cost_checks','quote_case_count','all_quote_cases_exact','instrument_function_ast_exact','instrument_pure_metadata_cases','runtime_original_module_count','runtime_all_only_allowed_change','clock_function_ast_exact','native_replay_initial_receipt_read','native_account_replayed')},ensure_ascii=False,indent=2))
