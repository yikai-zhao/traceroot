# Monotonic-clock provenance

TraceRoot calculates exclusive service time by subtracting nested child
intervals. This requires *parent and child timestamps from the same clock
origin*. Two independent Linux hosts can both report `CLOCK_MONOTONIC` while
having incomparable numerical timestamps.

An optional `clock_host_id` on **every** `service_span` event in the same trace
makes that assumption machine-checkable:

```json
{"id":"span-1","time_ns":1000000000,"kind":"service_span","source":"frontend","fields":{"trace_id":"t1","span_id":"root","service":"frontend","duration_ms":100,"operation":"GET /work","clock_domain":"local_monotonic","clock_host_id":"linux-boot-id-or-host-scope"}}
```

- Same nonempty host ID on every span of a trace: `consistent_reported_clock_host_id`.
- Two distinct IDs in one trace: **reject**, not guess.
- Partial identity (one span tagged, one untagged): **reject**.
- All absent (legacy local fixtures): accepted as
  `assumed_single_host_not_verified`, **not** claimed to be verified.

The intended identity is a common clock origin (for Linux experiments, a
boot-scoped ID obtained independently by each service is useful), **not**
merely a globally unique span or trace ID. IDs can be spoofed, so this is a
consistency guard rather than authenticated cross-host clock synchronization.

This deliberately does not attempt to infer real cross-host causal ordering.
Supporting cross-host traces properly requires an alternative representation
or clock-skew bounds; synchronized wall clocks alone are not a substitute for
validated interval arithmetic. The existing localhost HTTP demonstrations
predate the new identity field and remain explicitly marked unverified.

```bash
python3 -m unittest discover -s tests -p 'test_clock*.py' -v
```
