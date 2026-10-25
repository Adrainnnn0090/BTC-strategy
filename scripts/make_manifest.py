"""Freeze indexed delivery bytes; stage intended payload files before running.

Generated packaging metadata is environment-dependent and never release input.
Never touches the original ledger or model files.
"""
from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[1]
tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=R,text=True).split('\0'))
roots=('src','artifacts','models','training_inputs','strategies','research','provenance/studies')
files=[]
for base in roots:
 for p in sorted((R/base).rglob('*')):
  if not p.is_file()or'__pycache__'in p.parts or p.suffix in('.pyc','.pyo'):continue
  if any(x.endswith(('.egg-info','.dist-info'))for x in p.parts):continue
  if base=='strategies'and p.suffix=='.md':continue
  if str(p.relative_to(R))not in tracked:raise ValueError('Stage intended payload before freezing: '+str(p.relative_to(R)))
  files.append(dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
for name in ('provenance/runtime_adapter.json','provenance/pure_runtime_adapter.json','provenance/failure_index.json','pyproject.toml','uv.lock','requirements.lock','Dockerfile'):
 if name not in tracked:raise ValueError('Stage intended payload before freezing: '+name)
 p=R/name;files.append(dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
p=R/'provenance/release_manifest.json';p.write_text(json.dumps(dict(version=1,files=files,source_period=['2017-01-01','2025-12-31'],economic2026excluded=True,qualification='Delivery integrity snapshot, not new financial evidence; review/docs evolve separately.'),indent=2)+'\n')
print('RELEASE MANIFEST',len(files),'FILES',sum(r['bytes']for r in files),'BYTES')
