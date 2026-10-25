"""Supplement post-fill gross with quote-before-order gross, including exit days."""
from decimal import Decimal as D


def measure(account,fee):
    fee=D(str(fee));finance={r['date']:D(r['cost']) for r in account['financing']}
    assert len(finance)==len(account['financing'])
    prev=None;points=[];post=[];max_error=D(0)
    for m in account['marks']:
        q=D(m['signed_qty']);e=D(m['equity']);p=D(str(m['reference_price']))
        assert e>0
        post.append(dict(date=m['date'],signed_quantity=str(q),gross_pct=float(100*abs(q)*p/e)))
        if prev is not None and D(prev['signed_qty']):
            held=D(prev['signed_qty']);side='bid' if held>0 else 'ask';current=D(m[side]);old=D(prev[side])
            assert q in (held,D(0)),'same-quote reversal/rebalance unsupported'
            borrow=finance.get(m['date'],D(0));assert held<0 or borrow==0
            pre=D(prev['raw_cash'])-D(prev['financing_total'])-borrow+D(prev['unrealized_pnl'])+held*(current-old)-abs(held)*current*fee
            assert pre>0
            error=abs(pre-e);max_error=max(max_error,error);assert error<=D('.00000002')
            points.append(dict(date=m['date'],signed_quantity=str(held),equity=str(pre),gross_pct=float(100*abs(held)*p/pre)))
        else:assert finance.get(m['date'],D(0))==0
        prev=m
    def highest(items,short=False):
        values=[r for r in items if not short or D(r['signed_quantity'])<0]
        return max(values,key=lambda r:r['gross_pct']) if values else dict(date=None,gross_pct=0.)
    return dict(post_fill_whole=highest(post),post_fill_short=highest(post,True),
        before_or_after_whole=highest(points+post),before_or_after_short=highest(points+post,True),
        pre_order_points=points,max_equity_reconciliation_error=str(max_error),
        qualification='daily proxy quotes before/after orders;not intraday maximum or future cap')
