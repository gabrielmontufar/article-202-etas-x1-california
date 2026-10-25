"""Inspect archived results only; never fit, simulate or score."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
decision = json.loads((root / "results/R6/R6_DECISION.json").read_text(encoding="utf-8-sig"))
ns = json.loads((root / "results/R6/R6_DESCRIPTIVOS_N_S.json").read_text(encoding="utf-8-sig"))
upper = [decision["intervals"][str(k)]["bootstrap_t_95"][1] for k in (7, 14)]
expected = "NEGATIVO ROBUSTO" if all(x < 0.05 for x in upper) else "NEGATIVO NO ROBUSTO"
assert decision["decision"] == expected, "Archived rule/decision mismatch"
print(json.dumps({"scope": "Archived-output inspection, not numerical replication", "decision": decision["decision"], "IG": decision["IG_nats_per_event"], "upper_limits": upper, "NS": ns, "H08": "UNQUANTIFIED"}, indent=2))

