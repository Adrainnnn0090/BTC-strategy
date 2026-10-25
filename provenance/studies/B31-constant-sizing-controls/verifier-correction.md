# Additive verifier correction: one omitted non-economic source read

The frozen verifier stopped at its exact training-read-set assertion before account checks. Its expected set omitted this study's `spec.md`, which the registered source-hash check legitimately reads. All eight recorded training sets consist of the expected six entries plus precisely this one specification file. No test prices, current-year forecasts, economic accounts, other folds or reserved validation inputs appear in those training records.

Preserve `tools/verify_b31.py`, registration, original source hashes, policies, forecasts and accounts unchanged. Preserve the original failure in `original-verifier-failure.txt`; the dependent report's JSON parse failure is also retained. The report had not written any output when it stopped.

`tools/verify_b31_readset.py` copies the frozen verifier and adds only this already-permitted, already-hash-registered specification path to the exact expected set. All data-role assertions, scalar budget checks, control comparisons, account audits and the prescribed replay are byte-identical. This is an instrumentation correction, not a change to data permissions, strategy selection or results. Commit this explanation and companion before running it. Do not claim the original frozen verifier passed.

The companion's output and file hash are recorded in `verification.json`; the existing economic goal and consumed-history limitations remain unchanged. No new fitting or economic calibration is authorized by this correction.
