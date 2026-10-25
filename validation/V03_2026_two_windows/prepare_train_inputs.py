"""Materialize the exact past-only training mount; no validation inputs are read."""
import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path


def prepare(repo, out):
    repo, out = Path(repo).resolve(), Path(out).resolve()
    base = repo / 'validation/V03_2026_two_windows'
    if out.exists() and any(out.iterdir()):
        raise ValueError('refuse to overwrite training mount')
    out.mkdir(parents=True, exist_ok=True)
    sources = {
        'prices.json.gz': repo / 'artifacts/factors/prices.json.gz',
        'mining.json.gz': repo / 'artifacts/factors/mining.json.gz',
        'policies.json': base / 'preparation/policies-2026.json',
        'prior-policy-source-seal.json': base / 'preparation/prior-policy-source-seal.json',
        'prior-training-verification.json': base / 'preparation/prior-training-verification.json',
    }
    manifest = base / 'preparation/training-inputs.json'
    expected = json.loads(manifest.read_text())
    for name, src in sources.items():
        if hashlib.sha256(src.read_bytes()).hexdigest() != expected['files'][name]:
            raise ValueError('past-only source changed: ' + name)
    prices = json.loads(gzip.decompress(sources['prices.json.gz'].read_bytes()))
    if prices['days'][0] != '2017-01-01' or prices['days'][-1] != '2025-12-31':
        raise ValueError('training date boundary failed')
    for name, src in sources.items():
        shutil.copyfile(src, out / name)
    shutil.copyfile(manifest, out / 'manifest.json')
    print('PASS: exact sealed 2017--2025 training mount; validation not read')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default=str(Path(__file__).resolve().parents[2]))
    p.add_argument('--out', required=True)
    a = p.parse_args()
    prepare(a.repo, a.out)
