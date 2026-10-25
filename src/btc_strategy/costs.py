from decimal import Decimal,ROUND_DOWN,ROUND_UP
CASES={"BASE":(.001,.0005,1),"STRESS":(.003,.001,1),"SEVERE":(.005,.002,1),"DELAY":(.003,.001,2)}
BORROW={"BASE":.05,"STRESS":.1,"SEVERE":.3,"DELAY":.1}

def quote_prices(price, slip):
    price=Decimal(str(price));s=Decimal(str(slip));tick=Decimal('.01')
    return ((price*(1-s)).quantize(tick,rounding=ROUND_DOWN),(price*(1+s)).quantize(tick,rounding=ROUND_UP))
