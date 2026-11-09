#!/usr/bin/env python3
"""Repeatable local two-process HTTP regressions with independent intervention truth.

No downloads, internet, model, cloud, external ports, data-plane rewrite or CI.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

# Can be run from a source checkout without installing the package.
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from traceroot.core import read_events  # noqa: E402
from traceroot.traces import compare_runs  # noqa: E402


@contextmanager
def local_service(role: str, cpu_ms: float, backend_port: int = 0):
    command = [sys.executable, "-u", "-m", "traceroot.local_http", "--role", role,
               "--cpu-ms", str(cpu_ms), "--backend-port", str(backend_port)]
    env = dict(os.environ, PYTHONPATH=str(PROJECT / "src"))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
    try:
        # readline() is safe for this tiny local service, which prints readiness
        # immediately before entering serve_forever. Invalid configs exit early.
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f"{role} failed to start: {process.stderr.read()}")
        ready = json.loads(line)
        if ready["role"] != role or not 1 <= ready["port"] <= 65535:
            raise RuntimeError("invalid localhost readiness line")
        yield ready["port"]
    finally:
        process.terminate()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


@contextmanager
def cpp_backend(binary: Path, cpu_ms: float):
    command = [str(binary.resolve()), str(int(cpu_ms))]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f"C++ backend failed to start: {process.stderr.read()}")
        ready = json.loads(line)
        if ready["role"] != "backend" or not 1 <= ready["port"] <= 65535:
            raise RuntimeError("invalid C++ backend readiness")
        yield ready["port"]
    finally:
        process.terminate()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


def request(front_port: int, trace_id: str) -> dict:
    connection = HTTPConnection("127.0.0.1", front_port, timeout=4)
    try:
        connection.request("GET", "/work", headers={"X-Trace-Id": trace_id})
        response = connection.getresponse()
        data = response.read(8192)
        if response.status != 200:
            raise RuntimeError(f"frontend returned HTTP {response.status}: {data!r}")
        return json.loads(data)
    finally:
        connection.close()


def make_events(name: str, count: int, front_cpu_ms: float, back_cpu_ms: float,
                backend_binary: Path | None = None):
    events, cpu_costs = [], []
    with (cpp_backend(backend_binary, back_cpu_ms) if backend_binary else
          local_service("backend", back_cpu_ms)) as back_port:
        with local_service("frontend", front_cpu_ms, back_port) as front_port:
            for i in range(count):
                trace_id = f"{name.replace('_', '-')}-{i:02d}"
                obj = request(front_port, trace_id)
                child = obj["backend"]
                if obj["trace_id"] != trace_id or child["trace_id"] != trace_id:
                    raise RuntimeError("broken trace propagation")
                if not obj["start_ns"] <= child["start_ns"] <= child["end_ns"] <= obj["end_ns"]:
                    raise RuntimeError("child interval outside parent")
                for sid, part, service, parent in (
                        ("front", obj, "frontend", None),
                        ("backend", child, "backend", "front")):
                    fields = {"trace_id": trace_id, "span_id": sid,
                              "service": service, "operation": "GET /work",
                              "clock_domain": "local_monotonic",
                              "duration_ms": (part["end_ns"] - part["start_ns"]) / 1_000_000}
                    if parent is not None:
                        fields["parent_span_id"] = parent
                    events.append({"id": f"{trace_id}-{sid}", "time_ns": part["start_ns"],
                                   "kind": "service_span", "source": service, "fields": fields})
                cpu_costs.append({"trace_id": trace_id,
                                  "frontend_cpu_ms": round(obj["cpu_ns"] / 1e6, 3),
                                  "backend_cpu_ms": round(child["cpu_ns"] / 1e6, 3)})
    return events, cpu_costs


def experiment(output: Path, count: int = 7, back_extra_ms: float = 45,
               front_extra_ms: float = 45, backend_binary: Path | None = None) -> dict:
    if count < 3 or count > 100 or back_extra_ms < 25 or front_extra_ms < 25:
        raise ValueError("invalid experiment dimensions")
    output.mkdir(parents=True, exist_ok=True)
    interventions = {
        "baseline": {"frontend_cpu_ms": 1, "backend_cpu_ms": 2},
        "backend_regression": {"frontend_cpu_ms": 1, "backend_cpu_ms": 2 + back_extra_ms},
        "frontend_regression": {"frontend_cpu_ms": 1 + front_extra_ms, "backend_cpu_ms": 2},
        "negative_control": {"frontend_cpu_ms": 1, "backend_cpu_ms": 2},
    }
    files = {}
    observed_cpu = {}
    for name, c in interventions.items():
        events, cpu_costs = make_events(name, count, c["frontend_cpu_ms"], c["backend_cpu_ms"],
                                      backend_binary=backend_binary)
        f = output / f"{name}.jsonl"
        f.write_text(''.join(json.dumps(e, sort_keys=True) + '\n' for e in events))
        files[name] = f
        observed_cpu[name] = cpu_costs
    comparisons = {}
    for name, expected_service in (("backend_regression", "backend"),
                                   ("frontend_regression", "frontend"),
                                   ("negative_control", None)):
        base, base_sha = read_events(files["baseline"])
        candidate, candidate_sha = read_events(files[name])
        result = compare_runs(base, candidate)
        result["source_sha256"] = {"baseline": base_sha, "candidate": candidate_sha}
        comparisons[name] = result
        if expected_service is None:
            if result["decision"] != "no_threshold_regression_observed":
                raise RuntimeError(f"false positive in negative control: {result}")
        elif (result["decision"] != "regression_observed" or
              result.get("hypothesis", {}).get("service") != expected_service):
            raise RuntimeError(f"missed controlled {expected_service} regression: {result}")
    evidence = {
        "status": "PASS",
        "type": "real_two_process_localhost_http_intervention",
        "backend_runtime": "C++17" if backend_binary else "Python",
        "environment": {"kernel": platform.release(), "python": platform.python_version(),
                        "platform": platform.system(),
                        "allowed_cpus": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None},
        "requests_per_cohort": count,
        "interventions": interventions,
        "observed_cpu_ms_per_request": observed_cpu,
        "comparisons": comparisons,
        "limits": [
            "All services communicate through 127.0.0.1 on one host; monotonic clocks share that domain.",
            "This is intentionally injected CPU work, not an organically diagnosed production incident.",
            "Only sequential requests on local HTTP are measured, not concurrent service capacity.",
            "Measured spans are wall time; independently recorded CPU work is intervention evidence.",
            "A ranked exclusive-span contributor is not automatically proof of a root cause.",
            "No OTel collector, LLM agent, hardware profiler, production trace or external service.",
        ],
    }
    (output / "report.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("lab-output/real-http-regression"))
    p.add_argument("--count", type=int, default=7)
    p.add_argument("--cpp-backend", type=Path, help="compiled local C++17 backend binary")
    args = p.parse_args()
    result = experiment(args.output, args.count, backend_binary=args.cpp_backend)
    print(json.dumps({"status": result["status"], "requests_per_cohort": args.count,
                      "comparisons": {k: {"decision": v["decision"],
                                          "contributor": (v["hypothesis"] or {}).get("service"),
                                          "baseline_median_wall_ms": v.get("baseline_median_wall_ms"),
                                          "candidate_median_wall_ms": v.get("candidate_median_wall_ms")}
                                      for k, v in result["comparisons"].items()}}, indent=2))


if __name__ == "__main__":
    main()
