# Decision: reject these rank maps; retain fixed-budget risk alternatives

All six prespecified B30 rank-minus-constant comparisons lose return in every cost scenario and have higher worst drawdown. The simple constants dominate the corresponding rank rules on these historical measures. Stop tuning this rank-sizing family. This result does not establish that all forecast-strength methods fail: these constants are algebraic controls, not realized-exposure or risk matches, and the parent signals share market episodes.

All four constant variants exceed the earlier 2000% return screen and stay below the current 35% drawdown limit. Retain them as transparent risk-budget alternatives, with no claim of new predictive alpha:

| Variant | STRESS return % | Worst DD % | DELAY return % |
|---|---:|---:|---:|
| C01: Y01 × 0.875 | 3251.61 | 33.08748 | 1905.67 |
| C02: Y01 × 0.75 | 2417.21 | 31.89345 | 1489.41 |
| C03: H04 × 0.875 | 3176.44 | 33.08748 | 2131.81 |
| C04: H04 × 0.75 | 2390.43 | 31.89345 | 1637.24 |

Their unscaled parents retain higher returns in every cost case. At each fixed scale, Y01 has higher STRESS return and H04 has higher DELAY return at exactly the same worst DD. Keep both distinctions; do not pick a favorable cost case or claim one dominates the other. C02/C04 reduce parent worst DD by 2.38245 points. C01/C03 reduce it by 1.18842 points. These four risks still come from the shared 2019–2020 drawdown, not four independent crises.

All new opening dates, exit dates and reasons exactly match their unscaled parent in each cost scenario. The differences are opening budgets and later compounded quantities. The constants are active only in eligible 2020–2025 folds; 2018/2019 retain identity. C02 reduces 15/19 STRESS openings and C04 17/21. The unchanged 2019 portion is a material feature of this matched control and must not be relabeled as full-period 75% exposure.

Y01 remains the STRESS return leader at +4282.79% / 34.27590%; H04/H05 retain their higher-latency-return tradeoffs. None reaches the 10000% historical goal. Do not continue searching a dense scale grid to fit this history; return to bounded forecast-model research using strictly earlier matured observations.

All 52 final accounts completed; 36 exact controls matched and C02/STRESS replayed. Thirteen complete paths are distinct. 314 software tests passed before registration `1b258d1`; registration SHA256 `e73c1a6b9b5fac64f7ec972797caf17e176d305ced13444ad34ccedec54d71fa`. The original verifier failed on an omitted specification read; its code and failure remain preserved. The companion committed at `5eaa9ea` changes only that expected read path and passes the full audit. See [correction](verifier-correction.md) and [verification](verification.json). No strategy or account was modified to pass verification.

The source-timing assumptions, consumed design history and daily-price execution limits persist. June–September2026 validation remains excluded from all new research. No live promotion.
