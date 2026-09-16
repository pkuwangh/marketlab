# MarketLab Protect — Data-Driven Design Revision

## What the data says

Current `protect` is not a useful correction-timing signal yet.

- 88 protect days, or 42 distinct clusters (signals within 5 trading days grouped).
- 32/42 clusters had **no 5% SPY drawdown in the next 40 trading days**.
- Protect forward returns are essentially baseline: 20d +1.8% vs +1.3% all days; 40d +2.8% vs +2.5%.
- 10/42 clusters were **volatility-only confirmation**; 9/10 had no 5% drawdown in the next 40d.
- 8/42 clusters started after SPY was already >5% below its trailing 40d high.

Correction coverage is also poor. Using SPY peak-to-trough corrections >=5%, excluding COVID, only 4/14 episodes had a protect signal from 20 trading days before the peak through the first -5% crossing; even a 40-day window covers only 6/14.

## Why false positives happen

### 1. Weak setup can be rescued by extreme deterioration

Current logic is approximately:

```text
protect_strength = sqrt(stretch * deterioration)
```

There is no hard setup gate. A mediocre stretch score can therefore become `protect` when deterioration is extreme. More than half of protect days have stretch below the empirical stretch p90 (~0.49).

### 2. One family, especially volatility, can become the whole confirmation

Volatility-only signals are particularly weak: 9/10 distinct vol-only protect clusters did not precede a 5% drawdown within 40d.

A VIX/VVIX jump should raise alertness, but should not independently cause `protect`.

### 3. `stretch` mixes extension with fragility

Late protect signals reveal a semantic problem. After the market is already down, true extension/complacency is often gone, but breadth fragility, credit weakness, and yield-curve pressure still keep `stretch_pressure` positive.

All 8 protect clusters that began after a >5% trailing drawdown had weak trend-extension and vol-complacency components. Their “stretch” was coming from fragility-style inputs.

So `stretch_pressure` is not a clean protect setup.

## Why real corrections are missed

### 1. Setup and confirmation must coincide on the same day

The clearest example is 2018 Q4:

```text
Aug 29: stretch 0.57, deterioration 0.21 -> no action
Oct 11: stretch 0.22, deterioration 0.70 -> no action
```

The desired sequence occurred — extension first, deterioration later — but the current product rule cannot remember the earlier setup.

The 2024 summer correction shows the same problem in reverse: protect fired in June while the market was still near highs; when genuine deterioration arrived in late July/August, stretch had collapsed and the system returned `no_change`.

### 2. Many corrections are not preceded by high stretch at all

Of the 10 non-COVID corrections missed by the 20-day timing test:

- 4 had recent p90 stretch: primarily a temporal-memory failure.
- 6 had **no p90 stretch in the prior 40 trading days**.

Therefore an armed-stretch mechanism alone cannot solve the false-negative problem. Some corrections are regime breaks, not unwind-from-extension events.

## Revised protect design

### A. Split setup into `extension_setup` and `fragility`

`extension_setup` should represent actual extension/complacency only. Breadth/credit/liquidity weakness should be context or confirmation, not simultaneously counted as protect setup.

### B. Protect path 1: extension unwind

```text
high extension_setup
    -> arm for ~20-40 trading days with decay
    -> later broad deterioration
    -> protect
```

Use a rolling percentile threshold (roughly p90) rather than a fixed score such as 0.65.

Require at least two deterioration families, with at least one non-volatility/internal family. Volatility alone remains a warning.

### C. Protect path 2: regime break

Some genuine corrections have no preceding extension. Add a separate path that does **not** require stretch, but requires materially stronger broad deterioration — e.g. trend damage plus volatility and/or breadth/credit/liquidity confirmation.

This path should be deliberately harder to trigger than the extension-unwind path so event volatility cannot activate it by itself.

### D. Replace geometric compensation with hard gates

Do not allow very strong confirmation to compensate for an inadequate setup on the extension path.

```text
extension path:
    setup gate AND confirmation gate

regime-break path:
    broad deterioration gate
```

### E. Evaluate by correction episodes

Primary protect metrics should be:

- fraction of >=5% / >=8% corrections warned before the first -3% / -5% drawdown;
- median warning lead time;
- false-alert rate: no >=5% drawdown within 40d;
- whether the signal is early, timely, or already late.

Terminal 20d/40d return is secondary.

## Priority

1. Separate extension from fragility.
2. Add armed setup memory.
3. Add confirmation breadth; prohibit vol-only normal protect.
4. Add a distinct broad regime-break path for corrections without prior stretch.
5. Re-run episode-level correction coverage / false-alert analysis before tuning thresholds.

`redeploy` currently shows much stronger empirical behavior and should be left largely unchanged while protect is redesigned.
