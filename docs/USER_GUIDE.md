# User guide

The inspection example takes no arguments and resolves results relative to its own directory. Inputs are results/R6/R6_DECISION.json, R6_DESCRIPTIVOS_N_S.json and R6_IG_POR_ANO.csv. Output is a JSON summary on standard output with the archived decision, IG, interval limits and N/S records. It writes no files. Missing files, malformed JSON or disagreement between the recorded decision and its two-upper-limit rule produce an exception rather than a replacement result.

Historical numerical executors retain their original --stage interfaces, source locks and platform guards. They require the recorded inputs and paths; they are not invoked by the example. fit estimates historical parameters; generate produces daily controls and cascades; score reads closed forecasts and admitted counts. These interfaces are described for provenance, not authorised for execution in this preparation.

For typical review, inspect the two overall interval files, the complete annual CSV and the daily result CSV; retain both block lengths, all years and the final fraction. Do not select a favourable block length or year. The archived result must not be replaced by running a different code version.

