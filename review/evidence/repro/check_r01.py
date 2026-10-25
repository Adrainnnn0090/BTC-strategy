"""Round 01 deterministic read-only metadata/AST checks; no imports of research code."""
import ast
import gzip
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

SOURCE = Path('/workspace/BTCStrategyResearchLedger')
OWN = Path('/workspace/BTCExpertReview/workspaces/repro')
FORBIDDEN = ('2026', 'v01', 'v02')

def checked_read(path):
    path = Path(path)
    relative = str(path.relative_to(SOURCE)) if path.is_relative_to(SOURCE) else str(path)
    if any(x in relative.lower() for x in FORBIDDEN):
        raise ValueError('forbidden read path: ' + relative)
    return path.read_bytes()

def sha(path):
    return hashlib.sha256(checked_read(path)).hexdigest()

def read_json(path):
    raw = checked_read(path)
    return json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)

shared = Path('/workspace/BTCExpertReview/shared/source_manifest.json')
manifest = json.loads(shared.read_bytes())
manifest_hashes = {p: sha(SOURCE/p) == expected for p, expected in manifest['files'].items()}

seeds = ['lab/b109.py', 'lab/b88a.py', 'lab/b72.py', 'lab/b31.py']
pending = list(seeds)
visited = {}
absolute_literals = []
external_imports = set()
while pending:
    relative = pending.pop()
    if relative in visited:
        continue
    file = SOURCE/relative
    raw = checked_read(file)
    tree = ast.parse(raw, filename=relative)
    visited[relative] = hashlib.sha256(raw).hexdigest()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module:
                target = 'lab/' + node.module.replace('.', '/') + '.py'
                if (SOURCE/target).exists():
                    pending.append(target)
            elif node.level == 0 and node.module:
                external_imports.add(node.module.split('.')[0])
        elif isinstance(node, ast.Import):
            external_imports.update(n.name.split('.')[0] for n in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith('/workspace'):
            absolute_literals.append({'path': relative, 'line': node.lineno, 'literal': node.value})

studies = {
    'B109': 'B109-long-profit-local-coordinate',
    'B88A': 'B88A-short-net-loss-families',
    'B72': 'B72-cold-budget-exposure',
    'B31': 'B31-constant-sizing-controls',
}
registrations = {}
for name, folder in studies.items():
    reg = read_json(SOURCE/'studies'/folder/'registration.json')
    registrations[name] = {
        'recipes': [r['id'] for r in reg.get('recipes', [])],
        'versions': reg.get('versions'),
        'project_runtime_sources': reg.get('project_runtime_sources'),
        'estimator_runtime_sources': reg.get('estimator_runtime_sources'),
        'source_key_count': len(reg.get('source', {})),
        'inherited_sources_key_count': len(reg.get('inherited_sources', {})),
        'model_fits': reg.get('model_fits'),
    }

annual_states = {}
sample_schema = None
for year in range(2018, 2026):
    base = SOURCE/'studies'/studies['B88A']/'folds'/str(year)
    training = read_json(base/'training.json')
    states = training['model_states']
    valid = all(sha(base/p) == expected for p, expected in states.items())
    annual_states[str(year)] = {
        'cutoff': training['cutoff'], 'fits': training['fits'],
        'model_states_count': len(states), 'all_state_hashes_match': valid,
    }
    if year == 2025 and states:
        relative = sorted(states)[0]
        state = read_json(base/relative)
        sample_schema = {
            'path': str((base/relative).relative_to(SOURCE)),
            'keys': sorted(state), 'tree_count': len(state.get('trees', [])),
            'tree_keys': sorted(state['trees'][0]) if state.get('trees') else [],
        }

installed = {name: version(name) for name in registrations['B109']['versions']}
result = {
    'shared_manifest_all_7_match': len(manifest_hashes) == 7 and all(manifest_hashes.values()),
    'shared_manifest_hash_results': manifest_hashes,
    'seeds': seeds, 'static_local_import_closure_count': len(visited),
    'static_local_import_closure': dict(sorted(visited.items())),
    'absolute_workspace_literal_count': len(absolute_literals),
    'absolute_workspace_literals': sorted(absolute_literals, key=lambda r: (r['path'], r['line'])),
    'external_import_roots': sorted(external_imports),
    'registrations': registrations, 'b88a_annual_states': annual_states,
    'b88a_numeric_state_schema_sample': sample_schema,
    'installed_versions': installed,
    'installed_versions_match_b109': installed == registrations['B109']['versions'],
    'executed_research_modules': False, 'economic_observations_read': False,
    'writer_executed': False, 'forbidden_path_guard': list(FORBIDDEN),
}
with (OWN/'checks-r01.json').open('x') as stream:
    json.dump(result, stream, indent=2, ensure_ascii=False)
    stream.write('\n')
print(json.dumps({k: result[k] for k in (
    'shared_manifest_all_7_match', 'static_local_import_closure_count',
    'absolute_workspace_literal_count', 'external_import_roots',
    'registrations', 'b88a_annual_states', 'b88a_numeric_state_schema_sample',
    'installed_versions_match_b109')}, indent=2, ensure_ascii=False))
