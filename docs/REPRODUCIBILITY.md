# Reproducibility boundaries

1. Exact preserved outputs can be inspected with the included standard-library example and SHA256SUMS.json. This is documentary reproduction of the tables, not regeneration of the experiment.
2. Numerical reconstruction requires the frozen ComCat capture, admitted IDs, parent history, land/network masks, historical KDE, fits and all source-lock dependencies. The release excludes raw and derived scientific inputs while redistribution and source rights are unresolved. SCEDC boundary availability online was not treated as permission to redistribute it.
3. The historical run used Python 3.13.16, NumPy 2.5.4, SciPy 1.18.1, pyproj 3.8.0, Numba 0.68.0 and llvmlite 0.50.0. Historical Q3 reports NumPy 2.5.3; that discrepancy is retained. No new environment installation or full reproduction was tested for this release candidate.
4. Restore the ART and BOOT layouts described by the original source locks, keeping original scripts and hashes. R6 revision 3 accepts its carried revision-2 fit. It does not provide a certified clean-start revision-3 pipeline. Removing these guards would create a different implementation requiring separate review.
5. R6 daily generation historically totalled about 4.8 hours across 1025 receipts on the original host. This excludes some preparation and does not promise repeat runtime. Use bounded memory, one worker on the original 8 GB host, and separate output checkpoints. Never overwrite scientific inputs or results.
6. H08 has not been quantified. The included future plan is unapproved and unexecuted. The present user instruction prohibits launching new simulations.

The deterministic numerical-kernel example and saved-result inspection are supplied separately. No complete clean-start historical experiment or clean environment installation is certified. Provider access and redistribution limits are retained rather than relabelled as solved by code publication.


