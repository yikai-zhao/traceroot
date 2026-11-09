#!/usr/bin/env python3
"""Blind, read-only evaluation of latency-regression attribution on real sockets.

Ground truth is used to schedule an experiment and calculate the score, never to
select a trace feature, decision threshold, or hypothesized service. Failure
cases and negative controls are included in the reported denominator.

This is intentionally a *local controlled benchmark*, not an AI agent benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts"))
from traceroot.core import read_events  # noqa: E402
from traceroot.traces import compare_runs  # noqa: E402
from reproduce_http_regression import make_events  # noqa: E402

# Fixed, public experimental protocol; random sequence avoids repeated case order.
# Equal front/back regressions are not tested: the current analyzer does not
# yet justify choosing a unique primary contributor in ambiguous cases.
SCENARIOS = (
    ("backend", 1, 42),
    ("frontend", 42, 2),
    ("no_regression", 1, 2),
    ("subthreshold", 9, 2),
)
BASELINE_CPU = (1, 2)


def evaluate(output: Path, *, seeds: tuple[int, ...] = (11, 23, 37),
             requests: int = 5, cpp_binary: Path | None = None) -> dict:
    if not seeds or len(set(seeds)) != len(seeds) or not (3 <= requests <= 100):
        raise ValueError("invalid evaluation dimensions")
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for seed in seeds:
        run_order = list(SCENARIOS)
        random.Random(seed).shuffle(run_order)
        for index, (truth, front_cpu, back_cpu) in enumerate(run_order):
            # Opaque IDs: no label, service name, or intervention in file paths.
            case_id = f"s{seed:04d}-c{index:02d}"
            case_dir = output / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            baseline, base_cpu = make_events(
                f"{case_id}-baseline", requests, *BASELINE_CPU,
                backend_binary=cpp_binary)
            candidate, candidate_cpu = make_events(
                f"{case_id}-candidate", requests, front_cpu, back_cpu,
                backend_binary=cpp_binary)
            source = {}
            for name, rows in (("baseline", baseline), ("candidate", candidate)):
                file_path = case_dir / f"{name}.jsonl"
                file_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
                source[name] = {"sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                                "event_count": len(rows)}
            # Evaluation only reads the resulting JSONL, with labels withheld.
            observed_baseline, checked_base_sha = read_events(case_dir / "baseline.jsonl")
            observed_candidate, checked_cand_sha = read_events(case_dir / "candidate.jsonl")
            if (source["baseline"]["sha256"] != checked_base_sha or
                    source["candidate"]["sha256"] != checked_cand_sha):
                raise RuntimeError("trace integrity mismatch")
            diagnosis = compare_runs(observed_baseline, observed_candidate)
            if diagnosis["decision"] == "regression_observed":
                predicted = (diagnosis.get("hypothesis") or {}).get("service") or "undetermined"
            elif diagnosis["decision"] == "no_threshold_regression_observed":
                predicted = "no_regression"
            else:
                predicted = "abstained"
            expected = "no_regression" if truth in ("no_regression", "subthreshold") else truth
            record = {
                "case_id": case_id,
                "ground_truth_class": truth, "expected_result": expected,
                "predicted_result": predicted,
                "passed": predicted == expected,
                "trace_sources": source,
                "intervention": {"frontend_cpu_ms": front_cpu, "backend_cpu_ms": back_cpu},
                "observed_cpu": {"baseline": base_cpu, "candidate": candidate_cpu},
                "diagnosis": diagnosis,
            }
            cases.append(record)
            (case_dir / "decision.json").write_text(json.dumps(record, indent=2) + "\n")
    labels = ("backend", "frontend", "no_regression", "abstained", "undetermined")
    matrix = {truth: {p: 0 for p in labels} for truth in ("backend", "frontend", "no_regression", "subthreshold")}
    for case in cases:
        matrix[case["ground_truth_class"]][case["predicted_result"]] += 1
    report = {
        "protocol": "local_blind_controlled_span_attribution_v1",
        "backend": "C++17" if cpp_binary else "Python",
        "seeds": list(seeds), "requests_per_cohort": requests,
        "cases": cases, "cases_total": len(cases),
        "cases_passed": sum(c["passed"] for c in cases),
        "confusion_matrix": matrix,
        "accuracy": sum(c["passed"] for c in cases) / len(cases),
        "limits": [
            "Case labels were withheld from the analyzer but experiment types and thresholds are public.",
            "All controlled CPU interventions use localhost on one shared monotonic clock domain.",
            "No unseen production incidents, agent tool use, root cause proof or cross-host clock sync.",
            "A no-regression classification means the fixed thresholds were not exceeded.",
            "Results are host load dependent, and the evaluator retains all failed cases.",
            "No simultaneous multi-service fault or ambiguous-contributor classification is tested.",
        ]
    }
    (output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("lab-output/blind-evaluation"))
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 23, 37])
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--cpp-backend", type=Path)
    args = parser.parse_args()
    report = evaluate(args.output, seeds=tuple(args.seeds), requests=args.requests,
                      cpp_binary=args.cpp_backend)
    print(json.dumps({k: report[k] for k in ("cases_total", "cases_passed", "accuracy", "confusion_matrix")}, indent=2))
    return 0 if report["cases_total"] == report["cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
