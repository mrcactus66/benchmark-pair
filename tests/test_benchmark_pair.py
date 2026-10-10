import copy
import hashlib
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = "mrcactus66/benchmark-pair"
PREFIX = "https://raw.githubusercontent.com/" + REPO + "/" + "a" * 40 + "/examples/"
CONDITIONS = ["RasterSet r2, RGB 1024x1024 resized to 256x256 with bilinear interpolation",
              "Exactly one CPU thread and no GPU", "Request batch size is 1"]
BASE = (ROOT / "examples/baseline.txt").read_text()
GOOD = (ROOT / "examples/candidate-good.txt").read_text()


def extraction(label="Cedar v1", body=BASE, value="12.5", unit="ms"):
    return {"conditions": ["MATCH"] * 3,
        "condition_quotes": [f"Run {label} uses RasterSet r2: RGB images resized from 1024x1024 to 256x256\nwith bilinear interpolation.",
            "Execution uses one CPU thread, no GPU, and a\nrequest batch size of 1.",
            "request batch size of 1."], "metric": "MEDIAN", "value": value, "unit": unit,
        "measurement_quote": f"{label} median per-request latency was {value} {unit}",
        "sample_count": 1000, "sample_quote": f"{label} had 1000 timed requests.",
        "warmup": "EXCLUDED", "warmup_quote": "Its initial 50 warmup requests were excluded\nfrom both the timing and that sample count."}


def sources(bodies=(BASE, GOOD)):
    return [{"url": PREFIX + str(i) + ".txt", "sha256": hashlib.sha256(body.encode()).hexdigest()}
            for i, body in enumerate(bodies)]


@pytest.fixture
def contract(direct_deploy):
    return direct_deploy(str(ROOT / "contracts/benchmark_pair.py"), REPO, sdk_version="v0.2.12")


def register(contract, bodies=(BASE, GOOD), minimum=30, speedup=2500):
    contract.register("pair", "Cedar v1", "Cedar v2", json.dumps(CONDITIONS), minimum, speedup,
                      json.dumps(sources(bodies)))


def mock(direct_vm, bodies=(BASE, GOOD), rows=None):
    rows = rows or [extraction(), extraction("Cedar v2", GOOD, "10000", "us")]
    for i, (body, row) in enumerate(zip(bodies, rows)):
        direct_vm.mock_web("^" + re.escape(PREFIX + str(i) + ".txt") + "$", {"status": 200, "body": body})
        direct_vm.mock_llm('RUN: "Cedar v' + str(i + 1) + '"', json.dumps(row))


def read(contract):
    return json.loads(contract.get_review("pair"))


def test_comparable_cross_unit_pair_and_policy_commitment(contract, direct_vm):
    register(contract)
    mock(direct_vm)
    contract.review("pair")
    result = read(contract)
    assert result["status"] == "COMPARABLE"
    assert result["speedup_ppm"] == 1_250_000
    assert result["qualifies"] is True
    assert result["policy_sha256"] == hashlib.sha256(contract.get_pair("pair").encode()).hexdigest()
    assert contract.is_upgrade_admissible("pair")
    assert direct_vm.run_validator() is True


@pytest.mark.parametrize("threshold,qualifies", [(2499, True), (2500, True), (2501, False)])
def test_exact_improvement_boundary(contract, direct_vm, threshold, qualifies):
    register(contract, speedup=threshold)
    mock(direct_vm)
    contract.review("pair")
    assert read(contract)["qualifies"] is qualifies


def test_faster_batched_report_cannot_publish_speedup(contract, direct_vm):
    body = (ROOT / "examples/candidate-batched.txt").read_text()
    row = extraction("Cedar v2", body, "2", "ms")
    row["conditions"][2] = "DIFFERENT"
    row["condition_quotes"][1] = row["condition_quotes"][1].replace("size of 1.", "size of 16.")
    row["condition_quotes"][2] = "request batch size of 16."
    register(contract, bodies=(BASE, body))
    mock(direct_vm, bodies=(BASE, body), rows=[extraction(), row])
    contract.review("pair")
    assert read(contract)["status"] == "NOT_COMPARABLE"
    assert read(contract)["speedup_ppm"] == 0
    assert not contract.is_upgrade_admissible("pair")
    assert direct_vm.run_validator() is True


@pytest.mark.parametrize("warmup,status", [("UNKNOWN", "INCOMPLETE"), ("INCLUDED", "NOT_COMPARABLE")])
def test_warmup_must_be_explicitly_excluded(contract, direct_vm, warmup, status):
    body = GOOD + "\nWarmup was included in timed samples.\n"
    row = extraction("Cedar v2", body, "10000", "us")
    row.update(warmup=warmup, warmup_quote="" if warmup == "UNKNOWN" else "Warmup was included in timed samples.")
    register(contract, bodies=(BASE, body))
    mock(direct_vm, bodies=(BASE, body), rows=[extraction(), row])
    contract.review("pair")
    assert read(contract)["status"] == status
    assert not read(contract)["qualifies"]


def test_unknown_condition_withholds_comparison(contract, direct_vm):
    row = extraction("Cedar v2", GOOD, "10000", "us")
    row["conditions"][0], row["condition_quotes"][0] = "UNKNOWN", ""
    register(contract)
    mock(direct_vm, rows=[extraction(), row])
    contract.review("pair")
    assert read(contract)["status"] == "INCOMPLETE"


def test_sample_floor_is_enforced(contract, direct_vm):
    register(contract, minimum=1001)
    mock(direct_vm)
    contract.review("pair")
    assert read(contract)["status"] == "INSUFFICIENT_SAMPLES"
    assert not read(contract)["qualifies"]


def test_average_is_not_accepted_as_median(contract, direct_vm):
    body = GOOD.replace("median", "mean")
    row = extraction("Cedar v2", body, "10000", "us")
    row.update(metric="OTHER", measurement_quote=row["measurement_quote"].replace("median", "mean"))
    register(contract, bodies=(BASE, body))
    mock(direct_vm, bodies=(BASE, body), rows=[extraction(), row])
    contract.review("pair")
    assert read(contract)["status"] == "NOT_COMPARABLE"


def test_permissionless_review_owner_policy_and_no_replay(contract, direct_vm, direct_bob):
    with direct_vm.prank(direct_bob), direct_vm.expect_revert("Only owner"):
        register(contract)
    register(contract)
    with direct_vm.expect_revert("duplicate"):
        register(contract, speedup=1)
    mock(direct_vm)
    with direct_vm.prank(direct_bob):
        contract.review("pair")
    receipt = contract.get_review("pair")
    with direct_vm.expect_revert("already reviewed"):
        contract.review("pair")
    assert contract.get_review("pair") == receipt


@pytest.mark.parametrize("mutation", [
    {"value": "0"}, {"value": "-1"}, {"value": "1e3"}, {"unit": "ns"},
    {"value": "0.0001", "unit": "us"}, {"sample_count": True},
    {"conditions": ["MATCH"]}, {"condition_quotes": ["fake"] * 3},
    {"sample_count": 100}, {"measurement_quote": "Unrelated run ThumbnailPreview recorded 0.1 ms for a different input size."},
    {"warmup_quote": "An invented warmup statement"}, {"extra": "unsupported"},
])
def test_malformed_or_unanchored_report_aborts_without_receipt(contract, direct_vm, mutation):
    register(contract)
    row = {**extraction("Cedar v2", GOOD, "10000", "us"), **mutation}
    mock(direct_vm, rows=[extraction(), row])
    with direct_vm.expect_revert():
        contract.review("pair")
    assert not contract.is_upgrade_admissible("pair")


def test_hash_mismatch_is_retryable(contract, direct_vm):
    register(contract)
    mock(direct_vm, bodies=(BASE, "wrong bytes"))
    with direct_vm.expect_revert("hash mismatch"):
        contract.review("pair")
    assert not contract.is_upgrade_admissible("pair")
    direct_vm.clear_mocks()
    mock(direct_vm)
    contract.review("pair")
    assert contract.is_upgrade_admissible("pair")


def test_validator_independently_rejects_different_conditions(contract, direct_vm):
    register(contract)
    mock(direct_vm)
    contract.review("pair")
    direct_vm.clear_mocks()
    row = extraction("Cedar v2", GOOD, "10000", "us")
    row["conditions"][0] = "DIFFERENT"
    mock(direct_vm, rows=[extraction(), row])
    assert direct_vm.run_validator() is False


def test_forged_leader_quotes_hashes_and_facts_are_rejected(contract, direct_vm):
    register(contract)
    mock(direct_vm)
    contract.review("pair")
    for key, value in [("measurement_quote", "An invented measurement"),
                       ("sha256", "f" * 64), ("warmup", "UNKNOWN")]:
        forged = copy.deepcopy(read(contract)["reports"])
        forged[1][key] = value
        assert direct_vm.run_validator(leader_result=forged) is False
    assert direct_vm.run_validator(leader_result={"status": "COMPARABLE"}) is False
    assert direct_vm.run_validator(leader_error=RuntimeError("failed")) is False


@pytest.mark.parametrize("minimum,speedup", [(29, 1), (30, 0), (True, 100), (100, True)])
def test_invalid_sample_and_speedup_policies(contract, direct_vm, minimum, speedup):
    with direct_vm.expect_revert():
        register(contract, minimum=minimum, speedup=speedup)


@pytest.mark.parametrize("mutation", ["main", "../report.txt", "%2e%2e/report.txt", "outside", "duplicate"])
def test_unpinned_or_duplicate_sources_are_rejected(contract, direct_vm, mutation):
    manifest = sources()
    if mutation == "main":
        manifest[1]["url"] = manifest[1]["url"].replace("a" * 40, "main")
    elif mutation == "outside":
        manifest[1]["url"] = manifest[1]["url"].replace(REPO, "another/repo")
    elif mutation == "duplicate":
        manifest[1] = manifest[0]
    else:
        manifest[1]["url"] = PREFIX + mutation
    with direct_vm.expect_revert():
        contract.register("pair", "Cedar v1", "Cedar v2", json.dumps(CONDITIONS), 30, 100, json.dumps(manifest))


def test_missing_measurement_and_unknown_pair(contract, direct_vm):
    assert not contract.is_upgrade_admissible("pair")
    with direct_vm.expect_revert("Unknown pair"):
        contract.review("pair")
    register(contract)
    row = extraction("Cedar v2", GOOD, "10000", "us")
    row.update(value="", unit="", metric="UNKNOWN", measurement_quote="")
    mock(direct_vm, rows=[extraction(), row])
    contract.review("pair")
    assert read(contract)["status"] == "INCOMPLETE"
