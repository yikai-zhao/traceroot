"""Two deliberately small loopback HTTP services for measured regression reproduction.

This is an integration experiment, not a general tracing SDK or production server.
Both services run on one Linux host; time.monotonic_ns shares its clock domain.
"""
from __future__ import annotations

import argparse
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import time

_TRACE = re.compile(r"[a-zA-Z0-9-]{1,80}\Z")


def burn_cpu(milliseconds: float) -> tuple[int, int]:
    """Perform actual Python arithmetic for at least the requested *CPU time*.

    A monotonic wall-clock sleep would not test CPU contention/attribution.
    The result is intentionally host-dependent and not a CPU benchmark.
    """
    start = time.thread_time_ns()
    work = 0
    while (time.thread_time_ns() - start) < milliseconds * 1_000_000:
        for i in range(128):
            work = (work * 1664525 + i + 1013904223) & 0xffffffff
    return time.thread_time_ns() - start, work


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "TraceRootLocal/0.1"

    def log_message(self, *_args):
        pass

    def respond(self, status: int, data: dict):
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path != "/work":
            return self.respond(404, {"error": "not_found"})
        trace_id = self.headers.get("X-Trace-Id", "")
        if not _TRACE.fullmatch(trace_id):
            return self.respond(400, {"error": "bad_trace_id"})
        config = self.server.config
        start = time.monotonic_ns()
        if config.role == "backend":
            cpu_ns, checksum = burn_cpu(config.cpu_ms)
            end = time.monotonic_ns()
            return self.respond(200, {"trace_id": trace_id, "start_ns": start,
                                      "end_ns": end, "cpu_ns": cpu_ns, "checksum": checksum})
        try:
            conn = HTTPConnection("127.0.0.1", config.backend_port, timeout=3)
            try:
                conn.request("GET", "/work", headers={"X-Trace-Id": trace_id})
                response = conn.getresponse()
                body = response.read(8192)
                if response.status != 200:
                    return self.respond(502, {"error": "backend_non_200"})
                child = json.loads(body)
            finally:
                conn.close()
            if child.get("trace_id") != trace_id or not all(
                    type(child.get(k)) is int for k in ("start_ns", "end_ns", "cpu_ns")):
                return self.respond(502, {"error": "invalid_backend_trace"})
            cpu_ns, checksum = burn_cpu(config.cpu_ms)
            end = time.monotonic_ns()
            if not start <= child["start_ns"] <= child["end_ns"] <= end:
                return self.respond(502, {"error": "inconsistent_monotonic_clock"})
            return self.respond(200, {"trace_id": trace_id, "start_ns": start,
                                      "end_ns": end, "cpu_ns": cpu_ns, "checksum": checksum,
                                      "backend": child})
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return self.respond(502, {"error": "backend_unavailable_or_invalid"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=("frontend", "backend"))
    parser.add_argument("--cpu-ms", type=float, required=True)
    parser.add_argument("--backend-port", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.cpu_ms <= 250 or (args.role == "frontend" and not 1 <= args.backend_port <= 65535):
        parser.error("invalid CPU intervention or backend port")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.config = args
    # Explicit readiness signal; no arbitrary timing-based server startup race.
    print(json.dumps({"port": server.server_address[1], "role": args.role}), flush=True)
    try:
        server.serve_forever(poll_interval=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
