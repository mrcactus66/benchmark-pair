"""Verify saved transaction receipts and onchain reads before publishing."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
transactions = []
source = json.loads((EVIDENCE / "source.json").read_text())
contract_hash = hashlib.sha256((ROOT / "contracts/benchmark_pair.py").read_bytes()).hexdigest()
assert contract_hash == source["contract_sha256"]
operations = sorted(EVIDENCE.glob("*-transaction.json"))
assert len(operations) == 7
for path in operations:
    operation = json.loads(path.read_text())
    receipt_path = EVIDENCE / (operation["transaction_id"] + "-receipt.json")
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status_name"] in ("ACCEPTED", "FINALIZED")
    assert receipt["result_name"] == "MAJORITY_AGREE"
    assert receipt["leader_only"] is False
    assert receipt["value"] == 0
    assert any(r["mode"] == "leader" and r["execution_result"] == "SUCCESS" for r in receipt["executions"])
    if receipt["type"] == 1:
        assert receipt["deployed_source_sha256"] == contract_hash
    transactions.append({"operation": path.stem.replace("-transaction", ""),
        "transaction_id": receipt["hash"], "status": receipt["status_name"],
        "consensus": receipt["result_name"], "rotations": receipt["rotation_count"],
        "receipt": receipt_path.name})

expected = {"good": ("COMPARABLE", 1_250_000, True),
            "batched": ("NOT_COMPARABLE", 0, False), "missing": ("INCOMPLETE", 0, False)}
for case, values in expected.items():
    review = json.loads((EVIDENCE / (case + "-onchain.json")).read_text())
    assert (review["status"], review["speedup_ppm"], review["qualifies"]) == values
    for report, filename in zip(review["reports"], ("baseline.txt", "candidate-" + case + ".txt")):
        assert report["sha256"] == hashlib.sha256((ROOT / "examples" / filename).read_bytes()).hexdigest()
        assert report["url"] == "https://raw.githubusercontent.com/" + source["repository"] + "/" + source["commit"] + "/examples/" + filename

(EVIDENCE / "index.json").write_text(json.dumps({"network": "StudioNet", "chain_id": 61999,
    "fixtures": "synthetic", "source_sha256_verified": True, "results_verified": True,
    "transactions": transactions}, indent=2) + "\n", encoding="utf-8", newline="\n")
print("Verified seven zero-value consensus transactions, deployed source, and three onchain results.")
