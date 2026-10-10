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

There are 36 direct tests covering unit conversion, exact speedup thresholds,
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
