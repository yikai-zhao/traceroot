# Label-withheld C++/Python HTTP regression evaluation

**Measured on 2026-11-08, Linux localhost.** The evaluator is an offline deterministic trace comparator, **not an AI model**, autonomous agent, or production root-cause detector.

## Protocol

- Four condition types: C++ backend CPU work +40 ms, Python frontend CPU work +41 ms, identical service settings, and Python frontend +8 ms (below the published >=20 ms and >=25% wall-time regression threshold).
- Seeds **11, 23, 37** each randomize the four conditions. Each case has a *separately executed* four-request baseline and four-request candidate cohort. This yields 12 cases, 96 observed localhost HTTP requests, 192 linked spans. It is not 96 independent production incidents.
- An opaque case ID is used in trace files. Ground-truth condition labels and CPU interventions are not passed to `compare_runs`, which reads only validated JSONL; they are used after predictions for scoring. Full case records retain labels, both observed CPU times, evidence hashes, thresholds, diagnoses, successes and failures. The evaluation fails if any prediction does not match the held-out label.
- The comparator uses fixed public decision thresholds and exclusive wall-time accounting (union of child intervals); it does not learn or fit on this evaluation set.
- The new topology signature checks the **parent/child span shape**, not only the list of service names. A missing child, extra retry or changed call graph causes `insufficient_comparable_evidence`. Two adversarial topology tests validate the abstention path.

## Observations

| Ground-truth class | Cases | Correct | Decision |
|---|---:|---:|---|
| Backend slowdown | 3 | 3 | backend largest exclusive-time contributor |
| Frontend slowdown | 3 | 3 | frontend largest exclusive-time contributor |
| Unmodified negative control | 3 | 3 | no threshold regression |
| Below-threshold slowdown | 3 | 3 | no threshold regression |
| **Total** | **12** | **12** | **Controlled evaluation only** |

**Important:** 12/12 on this small controlled local set is **not** a production diagnosis accuracy estimate. There is one host/one shared monotonic clock domain; intentionally simple two-service requests; known CPU interventions; four requests/cohort; no background real-world failures, cross-host tracing, clock synchronization, OpenTelemetry or multicausal incidents. On a loaded host, retest and retain failure records rather than cherry-pick.

## Reproduce and inspect

```bash
g++ -O2 -std=c++17 -Wall -Wextra -Wpedantic examples/cpp_backend.cpp -o build/cpp_backend
python3 scripts/evaluate_blind_cases.py --cpp-backend build/cpp_backend \
  --output lab-output/blind-evaluation --seeds 11 23 37 --requests 4
python3 -m unittest discover -s tests -v
```

The script writes a JSONL baseline and candidate plus `decision.json` for *every* case and a final confusion matrix in `evaluation.json`. A minimal source-hash-linked sample summary is checked in under `evidence/`; full raw traces from this run are included in the accompanying local evaluation archive. No paid infrastructure or GitHub Actions is used.
