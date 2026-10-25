"""Derive presentation and independent arithmetic checks from sealed books only.

No predictions, refits, parameter choices or new portfolio paths are produced.
"""
import csv
import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / 'results'
ROSTER = ['LP35', 'TS04', 'ME01', 'MX03', 'B88A_S03', 'K02', 'Y01', 'C02', 'C04', 'BUY_HOLD']
WINDOWS = ['H1_TO_JUN29', 'JUN30_TO_OCT23', 'CONTINUOUS']


def book(window, strategy, case='STRESS'):
    return json.loads(gzip.decompress((OUT / 'accounts' / window / strategy / (case + '.json.gz')).read_bytes()))


def main():
    result = json.loads((OUT / 'results.json').read_text())
    seal = json.loads((OUT / 'validation-seal.json').read_text())
    for path, digest in seal['files'].items():
        assert hashlib.sha256((OUT / path).read_bytes()).hexdigest() == digest, path
    rows = result['results']
    assert len(rows) == 120 and len({(r['window'], r['strategy'], r['case']) for r in rows}) == 120
    assert result['validation_fitting_calls'] == result['model_selection_calls'] == 0
    counts = {'complete': 0, 'blocked': 0}
    derived = []
    for row in rows:
        if row['status'] != 'COMPLETE':
            assert row['strategy'] == 'C04'
            counts['blocked'] += 1
            continue
        counts['complete'] += 1
        assert row['independent_audit']['status'] == 'PASS'
        b = book(row['window'], row['strategy'], row['case'])
        eq = [Decimal(100)] + [Decimal(m['equity']) for m in b['marks']]
        high, dd = eq[0], Decimal(0)
        for e in eq:
            high = max(high, e)
            dd = max(dd, 1 - e / high)
        net = float(eq[-1] - 100)
        assert abs(net - row['metrics']['net_return_pct']) < 1e-8
        assert abs(float(dd * 100) - row['metrics']['max_daily_drawdown_pct']) < 1e-8
        longs = sum((Decimal(t['pnl']) for t in b['trades'] if t.get('direction', 1) == 1), Decimal(0))
        shorts = sum((Decimal(t['pnl']) for t in b['trades'] if t.get('direction', 1) == -1), Decimal(0))
        assert abs(longs + shorts - (eq[-1] - 100)) < Decimal('.0000001')
        derived.append(dict(window=row['window'], strategy=row['strategy'], case=row['case'],
                            long_realized_net_usdt=float(longs), short_realized_net_usdt=float(shorts)))
    assert counts == {'complete': 108, 'blocked': 12}
    equalities = []
    for window in WINDOWS:
        for case in ['BASE', 'STRESS', 'SEVERE', 'DELAY']:
            ref = book(window, 'LP35', case)
            for strategy in ['TS04', 'ME01', 'MX03']:
                b = book(window, strategy, case)
                for field in ['marks', 'fills', 'trades', 'financing']:
                    assert b[field] == ref[field], (window, case, strategy, field)
                equalities.append(dict(window=window, case=case, strategy=strategy,
                                       equals='LP35', fields=['marks', 'fills', 'trades', 'financing']))
    (BASE / 'tables').mkdir(exist_ok=True)
    flat = []
    for r in rows:
        flat.append({**{k: r[k] for k in ['window', 'strategy', 'case', 'status']}, **r.get('metrics', {}),
                     'excess_vs_buy_hold_percentage_points': r.get('excess_vs_buy_hold_percentage_points')})
    def save_csv(name, values):
        fields = list(dict.fromkeys(k for r in values for k in r))
        with (BASE / 'tables' / name).open('w', newline='') as f:
            w = csv.DictWriter(f, fields, lineterminator='\n'); w.writeheader(); w.writerows(values)
    save_csv('all_costs_and_windows.csv', flat)
    save_csv('realized_direction_decomposition.csv', derived)
    save_csv('raw_model_metrics.csv', result['prediction_metrics'])
    (BASE / 'verification/account-crosscheck.json').write_text(json.dumps(dict(
        status='PASS', method='Independent standard-library Decimal arithmetic from all saved marks/trades; no inference or fitting',
        counts=counts, checks=['120 unique registered rows', '108 prior independent audits PASS', 'all output SHA256',
                              'net returns', 'daily peak-to-trough drawdown', 'long+short net PnL reconciles ending cash'],
        path_identity_checks=equalities), indent=2) + '\n')
    for window in WINDOWS:
        print(window)
        for strategy in ROSTER:
            r = next(x for x in rows if x['window'] == window and x['strategy'] == strategy and x['case'] == 'STRESS')
            if r['status'] == 'COMPLETE':
                m = r['metrics']; print(f"{strategy}: {m['net_return_pct']:+.2f}% / DD {m['max_daily_drawdown_pct']:.2f}%")
            else:
                print(strategy, r['status'])


def chart():
    # Optional presentation dependency; never used by training or CI checks.
    import datetime
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams['svg.hashsalt'] = 'btc-v03-frozen-validation'
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharex='col', height_ratios=[2, 1])
    for col, (window, title) in enumerate(zip(WINDOWS[:2], ['Jan 1–Jun 29 (180 days)', 'Jun 30–Oct 23 (116 days)'])):
        for strategy in ['BUY_HOLD', 'LP35', 'B88A_S03', 'K02', 'Y01', 'C02']:
            b = book(window, strategy)
            dates = [datetime.date.fromisoformat(m['date']) for m in b['marks']]
            values = [float(m['equity']) for m in b['marks']]
            high = 100.; draws = []
            for v in values:
                high = max(high, v); draws.append(100 * (v / high - 1))
            label = 'LP35 = TS04 = ME01 = MX03' if strategy == 'LP35' else strategy
            axes[0, col].plot(dates, values, label=label, linewidth=1.5)
            axes[1, col].plot(dates, draws, linewidth=1.2)
        axes[0, col].set_title(title)
        axes[0, col].axhline(100, color='gray', lw=.6)
        axes[0, col].set_ylabel('Net equity (initial 100 USDT)')
        axes[1, col].set_ylabel('Drawdown (%)')
        axes[0, col].legend(fontsize=7)
        for row in range(2): axes[row, col].grid(alpha=.2)
        axes[1, col].tick_params(axis='x', rotation=25)
    fig.suptitle('Frozen 2026 validation · STRESS costs · fresh cash per window\nDaily USD reference proxy; conditional PIT; reused validation, not a fresh blind test', fontsize=11)
    fig.tight_layout()
    (BASE / 'figures').mkdir(exist_ok=True)
    fig.savefig(BASE / 'figures/stress_equity_and_drawdown.svg', metadata={'Date': None})
    svg = BASE / 'figures/stress_equity_and_drawdown.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('--chart', action='store_true'); a = p.parse_args()
    main()
    if a.chart: chart()
