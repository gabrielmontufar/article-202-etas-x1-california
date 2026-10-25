# ETAS-X1 California: source and saved-result companion

This companion accompanies Article 202, a preregistered ETAS-X1 comparison followed by specification robustness analysis. It contains preserved scientific source, closed result files, protocol records and English usage documentation. Q2 remains FAIL_SEUDOPROSPECTIVO. R6 remains NEGATIVO NO ROBUSTO: no statistically conclusive gain was detected, and the 0.05 nats/event bound was not robust to the ETAS specification. Both models retain N/S inconsistencies. Monte Carlo error of the 500-trajectory means remains unquantified (H08).

## Inspect the reported result

Requires Python's standard library only:

    python examples/inspect_saved_results.py

This reads the closed R6 result and checks its saved decision against both upper limits; it does not regenerate forecasts or rescore IG. Output is JSON on standard output.

## Deterministic numerical example

In an isolated environment with NumPy and SciPy installed (recorded pins: requirements-example.txt):

    python examples/deterministic_kernel_example.py

This exercises the preserved temporal/radial CDFs and polygon integrator against analytic values in a dummy Cartesian case, with absolute tolerance 1e-12. Optional input: --fixture PATH. See docs/DETERMINISTIC_EXAMPLE.md for inputs, expected outputs, errors and scope. It draws no random values, fits no parameters and computes no forecast or IG score. Its local receipt is in provenance/DETERMINISTIC_EXAMPLE_RESULT.json. An existing environment was checked; a new clean environment was not installed for this release.

## Contents

- source/ART: article executors, historical ETAS/ETAS-X1 kernels, Q1/Q2/Q3 and R6 source.
- source/BOOT: original fitting and acceleration modules and bootstrap metadata.
- results/R5 and results/R6: closed summaries, R6 daily/annual values and fit receipts.
- protocol: original Spanish protocol records; the usage documentation and source comments are in English.
- provenance: source locks, copy records and bounded verification receipts.
- docs: installation/use, data access, licences and reproducibility limits.

## Reconstructing the historical experiment

Read docs/REPRODUCIBILITY.md, docs/DATA_ACCESS.md and docs/RELEASE_LIMITS.md. The historical executors retain Windows paths, source locks and guards. The frozen catalogue, derived histories and geographic inputs are not bundled; provider access information and input hashes are retained. A later provider query is not the same frozen capture. Complete clean-start numerical reproduction is not certified, particularly across R6's carried revision-2 fit. Do not remove the original guards to make an unreviewed executable version.

This public package permits source inspection, saved-result inspection and the deterministic kernel example. It does not establish blinded/prospective validity, baseline adequacy, operational skill or resolution of H08. The author has requested no additional simulations.

## Licensing

Original code: MIT (LICENSE). Original documentation: CC BY 4.0 (LICENSE_DOCUMENTATION.md). Third-party notices are retained; see LICENSING.md. No raw third-party catalogues, boundaries, manuscript drafts or correspondence are included.

SHA256SUMS.json identifies the release files, excluding itself. Scientific source and saved results are preserved byte for byte from the approved local proposal. Hashes verify file identity, not scientific approval or predictive validity.
