# ChemLab reaction-conversion fixture

Source: HICAI-ZJU/SciToolAgent, `ToolsAgent/TempFiles/ChemLab/`
(demo_train_Morgan_fingerprints.csv, demo_test_Morgan_fingerprints.csv).

License: MIT, Copyright (c) 2024 Jing Yu. The upstream LICENSE text is
included in the source repository at `oss/full/HICAI-ZJU__SciToolAgent/LICENSE`.

Purpose: local, frozen protocol-validation data for S5 run/EA/claim wiring.
It is not a novel scientific result and must not be presented as this thesis's
experimental evidence. Features are 512-bit Morgan fingerprints (B and C
reactants); target is LCAP conversion.

## Derived held-out split

`holdout_train_Morgan_fingerprints.csv` (376 rows) and
`holdout_test_Morgan_fingerprints.csv` (42 rows) are derived from
`demo_train_Morgan_fingerprints.csv` by ranking rows on SHA-256 of their
fields and taking the first 42 as the held-out test set. The holdout is
disjoint from `demo_test_Morgan_fingerprints.csv` (verified by row hash) and
was never used as test data during admission. It is used only for post-lease
S5 seed-budget confirmation; results remain protocol validation, not thesis
evidence.

- holdout_test SHA-256: `c5bad4acf99bc65e233d4f37fa4d54c565c154e2b1da889164ce8f77fe4ccdd0`
- holdout_train SHA-256: `1c2b17da7ad50a08c727c8ed57966ec1f445c58de8db1408d21ba3004371668d`
