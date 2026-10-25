"""Original retained-source reader with explicit endpoint, no terminal-policy overwrite."""
from .io import sha

def load_bank(base, days, reader, last=2025):
    where = {d: i for i, d in enumerate(days)}; scores = {}; policies = {'U02': {}, 'U04': {}, 'Y01': {}}
    choices = {'H03': {}, 'H04': {}}; ranks = {'Y01': [None]*len(days), 'Y04': [None]*len(days)}
    active = {k: [False]*len(days) for k in ranks}
    flags = {k: [False]*len(days) for k in ('bear', 'negative20', 'available')}
    for year in range(2018, last+1):
        folder = base/'folds'/str(year)
        seal, training, receipt = [reader(folder/n) for n in ('seal.json', 'training.json', 'test-receipt.json')]
        assert seal['cutoff'] == training['cutoff'] == f'{year-1}-12-31' and not seal['current_test_read']
        assert sha(folder/'training.json') == seal['training_sha256']
        assert sha(folder/'seal.json') == receipt['seal_sha256']
        assert sha(folder/'predictions.json.gz') == receipt['predictions_sha256']
        assert not receipt['reserved_validation_read'] and receipt['fitting_calls'] == 0
        forecast = reader(folder/'predictions.json.gz')
        assert forecast['dates'] == days[where[f'{year-1}-12-31']:where[f'{year}-12-31']]
        for name, values in forecast['scores'].items():
            scores.setdefault(name, [None]*len(days))
            for day, value in zip(forecast['dates'], values, strict=True):
                scores[name][where[day]] = value
        for name in ('U02', 'U04'):
            policies[name][year] = training['parent_policies'][name]
        if 'y01_policy' in training:
            policies['Y01'][year] = training['y01_policy']
        for name in choices:
            if 'parent_choices' in training:
                choices[name][year] = training['parent_choices'][name]
        if 'active' in training:
            assert forecast['active'] == training['active']
            for name, values in forecast['ranks'].items():
                for day, value in zip(forecast['dates'], values, strict=True):
                    ranks[name][where[day]] = value
                    active[name][where[day]] = training['active'][name]
        for day in forecast['dates']:
            flags['available'][where[day]] = True
        for name, values in forecast.get('short_flags', {}).items():
            for day, value in zip(forecast['dates'], values, strict=True):
                flags[name][where[day]] = value
    return dict(scores=scores, policies=policies, flags=flags, choices=choices, ranks=ranks, active=active)
