# Benchmark pair

Two latency numbers do not establish a speedup if the workload or measurement
method changed. This GenLayer contract reviews the comparability of two prose
benchmark reports before allowing a consumer to use their ratio.

## Contract

The deployer sets a source repository and registers each pair once. Registration
freezes the two run labels, two to six required test conditions, minimum timed
sample count, minimum speedup in basis points, and two commit-pinned report URLs
with SHA-256 commitments. Anyone can review a registered pair. Completed reviews
cannot be replaced.

Leader and validators independently fetch both reports and classify each
condition as MATCH, DIFFERENT, or UNKNOWN. They also extract the selected run's
latency, statistic, timed sample count, and treatment of warmup. Quotations must
exist verbatim in the report. Leader quotations are checked against freshly
fetched bytes before validators compare their own facts; matching schema is
insufficient. The comparison tolerates different valid quote spans, not different
methodology, samples, or measurements.

Only median per-request latency with explicitly excluded warmup is eligible.
Seconds, milliseconds and microseconds become whole nanoseconds using integer
arithmetic. A decimal must retain exact nanosecond precision. No floating point
calculation or model-generated speedup is used.

| Review status | Consumer result |
| --- | --- |
| NOT_COMPARABLE | Explicit condition mismatch, other statistic, or included warmup |
| INCOMPLETE | Missing condition, measurement, sample count, or warmup statement |
| INSUFFICIENT_SAMPLES | Both reports are complete but a sample count is below policy |
| COMPARABLE | Ratio may be reported; speedup threshold is checked separately |

Non-comparable reviews publish `speedup_ppm=0` and `qualifies=false`. For a
comparable pair, `speedup_ppm` is the floor of baseline/candidate times one
million. The qualifying decision uses exact cross multiplication, avoiding a
rounded ratio at the threshold. `is_upgrade_admissible(pair_id)` returns false
before review and unless the pair is comparable and meets that threshold.

## Test locally

Use Python 3.13, activate a virtual environment, then:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
genvm-lint lint contracts/benchmark_pair.py
```

There are 37 direct tests covering unit conversion, exact speedup thresholds,
batch-size mismatch, sample floors, missing methodology, non-median statistics,
owner control, immutable reviews, malformed extractions, decoy measurements,
hash mismatch, and independent validator disagreement. The actual contract runs
through `gltest` storage and calldata; web and model answers are mocked.
They do not reproduce a distributed network or measure a real program.

The header pins the GenVM Python runner; direct tests use official v0.2.12
artifacts. Windows open-file cleanup in `tests/conftest.py` and the bounded
GitHub-source checks reuse support patterns from
[deprecation-notice-check](https://github.com/mrcactus66/deprecation-notice-check).
The benchmark extraction, comparison policy, decision logic and tests are separate.

## Limits

This checks reported methodology, not actual hardware, execution, or performance.
The owner can omit an important required condition or supply misleading reports.
Commit pinning binds bytes, not truth. A minimum sample count is a policy guard,
not statistical significance or a confidence interval. Exact fact agreement may
fail on ambiguous prose. Unsupported units and sub-nanosecond precision are
rejected rather than rounded.

The Cedar reports in `examples/` are synthetic. They demonstrate a valid
cross-unit comparison, an incompatible batch size, and missing warmup details.
The contract moves no tokens and makes no automatic deployment change.

## Studio evidence

Final contract: [0xD27df300C3F2235d8a785edb3D76C897Ae26ddAD](https://explorer-studio.genlayer.com/address/0xD27df300C3F2235d8a785edb3D76C897Ae26ddAD).
The deployed source matches `contracts/benchmark_pair.py` at commit
`ec166d8af7eaad5efe3e222f825e52b7757f8513`.

The demonstration fixes a 100-sample minimum and a 1.20x minimum speedup.
Its three onchain reads are:

| Pair | Result | Ratio | Upgrade admissible |
| --- | --- | --- | --- |
| good | COMPARABLE | 1.25x | true |
| batched | NOT_COMPARABLE | Withheld | false |
| missing | INCOMPLETE | Withheld | false |

All seven final transactions (deployment, three registrations, three reviews)
reached ACCEPTED or FINALIZED with MAJORITY_AGREE and successful leader
execution. The good review required one leader rotation. Quorum-cancelled
validators and any differing votes remain in the readable receipts. These
examples demonstrate majority agreement, not unanimity.

[`evidence/index.json`](evidence/index.json) maps operations to transaction IDs
and receipts. Evidence includes source hashes, input policies, consensus votes,
execution results, and onchain reviews. Full RPC receipts remain locally in
ignored `.local/raw-receipts`; repeated storage/source encodings, signatures,
and routing configuration are omitted from the public summaries. Explorer
links are provided for independent inspection. Studio state is temporary.

To reproduce on gasless StudioNet, use `scripts/studio_demo.py`: deploy, wait
for deployment, then register each of `good`, `batched`, `missing`. Wait for each
registration before reviewing it; wait again before reading the result.
The script generates a disposable account and stores its key only in ignored
`.local/studio.key`. It automatically records the contract address after a
successful deployment inspection. Example:

```sh
python scripts/studio_demo.py deploy
python scripts/studio_demo.py wait <deployment-transaction-id>
python scripts/studio_demo.py register good
python scripts/studio_demo.py wait <registration-transaction-id>
python scripts/studio_demo.py review good
python scripts/studio_demo.py wait <review-transaction-id>
python scripts/studio_demo.py read good
```

After all three cases, `python scripts/verify_evidence.py` checks deployed source,
all seven zero-value transactions, report commitments, and expected results
before producing the evidence index. The documents and account are
operator-controlled fixtures; no independent benchmark or real user adoption
is claimed.
