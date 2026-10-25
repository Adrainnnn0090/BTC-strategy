"""Original literal paper metadata; no exchange API or current-filter claim."""
from decimal import Decimal
from nautilus_trader.model import InstrumentId,Venue,CurrencyPair,Symbol,Currency,Price,Quantity,Money
INSTRUMENT=InstrumentId.from_str("BTCUSDT.BINANCE")
VENUE=Venue("BINANCE")

def paper_instrument(ts):
    """Literal local metadata; never claimed to be current venue filters."""
    return CurrencyPair(instrument_id=INSTRUMENT, raw_symbol=Symbol("BTCUSDT"),
        base_currency=Currency.from_str("BTC"), quote_currency=Currency.from_str("USDT"),
        price_precision=2, size_precision=5, price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.00001"), min_quantity=Quantity.from_str("0.00001"),
        min_notional=Money.from_str("5 USDT"), margin_init=Decimal(0), margin_maint=Decimal(0),
        maker_fee=Decimal("0.001"), taker_fee=Decimal("0.001"), ts_event=ts, ts_init=ts)
