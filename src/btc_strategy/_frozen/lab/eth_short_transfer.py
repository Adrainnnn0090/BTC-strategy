"""Original ETH54lag7 recipe in three fixed short-model source controls."""
from .eth_factors import append_eth

GROUPS=('PAD54','SELF54','ETH54')


def features(days,prices,eth):
    if len(days)!=len(prices)or len(eth)!=len(days):raise ValueError('ETH transfer alignment')
    same=[dict(date=r['date'],price_usd=str(p)if r['price_usd']is not None else None)for r,p in zip(eth,prices,strict=True)]
    return dict(PAD54=append_eth(days,prices,eth,7,'PAD54'),SELF54=append_eth(days,prices,same,7,'ETH54'),ETH54=append_eth(days,prices,eth,7,'ETH54'))
