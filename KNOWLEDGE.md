# MarketLab Knowledge

This file explains the market-regime evidence shown by:

```bash
./bin/marketlab regime snapshot --detail
```

These notes are a general reference for the indicators MarketLab watches. They are
research heuristics, not investment advice.

## Market Signals Table

Ranges below are practical rules of thumb, not hard-coded model thresholds. MarketLab
uses rolling percentiles in the pressure table to decide what is unusually stretched
or washed out versus recent history.

| Family | Indicator | What it is | Typical ranges | What does it indicate? |
| --- | --- | --- | --- | --- |
| Trend | SPY | SPDR S&P 500 ETF Trust. A broad large-cap U.S. equity proxy. | 20d return: around -3% to +5% is ordinary; above +8% is stretched; below -8% is a sharp selloff. Distance from 50d moving average: around -3% to +5% is ordinary; above +8% is extended; below -5% shows trend damage. | Rising SPY above its moving averages means the broad market trend is healthy. Very strong gains can also mean the market is crowded or stretched. Falling SPY or negative moving-average distance means broad-market deterioration. |
| Trend | QQQ | Invesco QQQ ETF. A Nasdaq-100 / large growth and technology proxy. | Similar to SPY, but QQQ normally moves more. A +10% 20d gain or +10% distance above the 50d average is stretched; a -10% 20d move or deep break below the 50d average is meaningful damage. | QQQ leadership usually means growth/tech risk appetite is strong. QQQ lagging SPY warns that leadership is weakening even if the headline index still looks fine. |
| Volatility | VIX | Cboe Volatility Index. It measures roughly 30-day expected S&P 500 volatility implied by options. | Below 12 is very calm/complacent; 12-20 is normal to calm; 20-30 is elevated; above 30 is stressed; above 40 is crisis-like. | Low VIX means options markets price little near-term index turbulence. High VIX means fear, hedging demand, or expected volatility is elevated. Low but rising VIX can be an early de-risk warning. |
| Volatility | SPY rv20 | SPY 20-day realized volatility. This is what SPY has actually been doing, annualized from recent daily moves. | Below 10% is quiet; 10-20% is normal; 20-30% is elevated; above 30% is stressed. | Low realized volatility means the tape has been stable. High realized volatility means actual price movement is unstable, even if implied volatility has not fully caught up. |
| Volatility | VVIX | Cboe VVIX Index, often described as volatility of VIX. It proxies how much volatility traders expect in VIX itself. | Below 90 is calm; 90-110 is normal/mixed; above 120 is stressed; above 150 is extreme. | Low VVIX means volatility expectations are stable. High VVIX means traders are paying for convexity around volatility itself. Rising VVIX while VIX is still low is an important early-warning pattern to study. |
| Volatility | VIX9D/VIX | VIX9D is Cboe's 9-day expected S&P 500 volatility index. This ratio compares 9-day implied volatility to VIX's roughly 30-day implied volatility. | Below 0.90 is calm near term; 0.90-1.00 is normal; 1.00-1.10 means near-term volatility is getting expensive; above 1.10 is near-term stress. | A low ratio means the immediate future is priced calmer than the next month. A high ratio means traders are paying up for near-term event risk or immediate protection. |
| Volatility | VIX/VIX3M | VIX3M is Cboe's 3-month expected S&P 500 volatility index. This ratio compares 30-day implied volatility to 3-month implied volatility. | Below 0.85 is deep contango/calm; 0.85-1.00 is normal contango; above 1.00 is backwardation/stress; above 1.10 is more severe stress. | Below 1.0 means near-term volatility is below longer-term volatility, which is the normal calm structure. Above 1.0 means near-term risk is priced above longer-term risk, often seen during selloffs. |
| Breadth | RSP/SPY | RSP is the equal-weight S&P 500 ETF. RSP/SPY compares average-stock performance with cap-weighted S&P 500 performance. | Around -1% to +1% over 20d is neutral. Above +2% is broadening participation. Below -2% is narrowing participation; below -4% is significant concentration risk. | RSP outperforming SPY means more stocks are participating, not just the largest names. RSP lagging SPY means the index may be held up by mega-cap concentration. |
| Breadth | IWM/SPY | IWM is the iShares Russell 2000 ETF. IWM/SPY compares small caps with large caps. | Around -2% to +2% over 20d is ordinary. Above +3% shows broad cyclical risk appetite. Below -3% shows small-cap weakness; below -5% is material risk-off breadth. | IWM outperforming SPY usually means risk appetite is broadening into smaller, more cyclical companies. IWM lagging SPY means the rally is less inclusive and often more fragile. |
| Breadth | S&P 500 above 50d MA | Percent of S&P 500 stocks above their 50-day moving average. In local data this is `$S5FI`. | Above 70% is strong/broad but can become stretched; 50-70% is healthy; 40-50% is mixed; below 40% is weak; below 25% is washout territory. | High values mean many stocks are in intermediate uptrends. Very high values can mean broad strength or overextension. Low values mean internal damage even if the index level has not fallen much. |
| Breadth | S&P 500 above 200d MA | Percent of S&P 500 stocks above their 200-day moving average. In local data this is `$S5TH`. | Above 70% is broad long-term strength; 55-70% is healthy; 40-55% is mixed; below 40% is weak; below 25% is major trend damage/washout. | This is slower than the 50d version and better for major trend health. Low values mean many stocks have broken long-term trend. Recovering from very low levels can mark improving market repair. |
| Credit | HYG/TLT | HYG is a high-yield corporate bond ETF. TLT is a long-duration U.S. Treasury ETF. HYG/TLT compares risky credit with defensive Treasury duration. | Around -1% to +1% over 20d is neutral. Above +1% shows credit risk appetite. Below -2% is defensive; below -4% is notable credit/rates stress. | HYG outperforming TLT means investors prefer credit risk over government-bond safety. HYG lagging TLT means demand for safety or concern about credit risk is rising. |
| Credit | HY OAS | High-yield option-adjusted spread. MarketLab uses FRED `BAMLH0A0HYM2`, the ICE BofA U.S. high-yield spread over a Treasury curve. | Below 3.5% is tight/calm; 3.5-5.0% is normal/mixed; 5-7% is stressed; above 7% is high stress; above 10% is crisis-like. | Low/tight spreads mean investors demand little extra yield for junk-bond risk. That is supportive until it becomes complacent. High or widening spreads mean credit stress and tighter funding. |
| Liquidity | NFCI | Chicago Fed National Financial Conditions Index. It summarizes U.S. financial conditions across money markets, debt/equity markets, banking, and shadow banking. | Below -0.50 is very loose; -0.25 to +0.25 is near average; above +0.25 is tight; above +0.75 is stressed; above +1.00 is severe. | Negative NFCI means easier-than-average financial conditions. Positive NFCI means tighter-than-average conditions. Rising NFCI means liquidity is worsening; falling NFCI means liquidity is improving. |
| Rates | 10y-2y yield curve | The 10-year Treasury yield minus the 2-year Treasury yield. Values are percentage points. | Above +1.00pp is steep/normal; +0.50pp to +1.00pp is healthy; 0 to +0.50pp is flat; below 0 is inverted; below -0.50pp is deeply inverted. | A positive slope is a more normal growth/rates backdrop. A flat or inverted curve often signals restrictive policy, growth concern, or late-cycle stress. A steepening curve can be healthy after normalization, but a violent bear steepening can also pressure equities. |

## Pressure Extremes

The pressure table is a separate layer from the educational ranges above. Each raw
feature is ranked against its recent point-in-time history, currently up to 252
observations where available.

Pressure labels are:

| Pressure value | Label |
| --- | --- |
| `< 0.30` | low |
| `0.30-0.55` | noticeable |
| `0.55-0.70` | elevated |
| `0.70-0.85` | high |
| `>= 0.85` | extreme |

For a single percentile-normalized feature, `>= 0.85` is roughly the most stretched or
most washed-out 7.5% of its rolling lookback. For multi-feature modules, pressure is
averaged by family, so the final pressure score is smoother than any one raw input.

## External Definition Sources

- Cboe VIX and volatility term structure:
  https://www.cboe.com/tradable-products/vix,
  https://www.cboe.com/tradable-products/vix/term-structure/,
  https://www.cboe.com/insights/posts/what-the-vix-and-vix-1-d-indices-attempt-to-measure-and-how-they-differ/
- FRED high-yield OAS:
  https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- Chicago Fed / FRED NFCI:
  https://www.chicagofed.org/research/data/nfci/current-data,
  https://fred.stlouisfed.org/series/NFCI
- FRED Treasury constant maturity yields:
  https://fred.stlouisfed.org/series/DGS10,
  https://fred.stlouisfed.org/series/DGS2
- ETF product pages:
  https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy,
  https://www.invesco.com/qqq-etf/en/about.html,
  https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-500-equal-weight-etf.html,
  https://www.ishares.com/us/products/239710/ishares-russell-2000-etf,
  https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf,
  https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf
- Percent-above-moving-average breadth concept:
  https://chartschool.stockcharts.com/table-of-contents/market-indicators/percent-above-moving-average
