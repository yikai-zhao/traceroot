# Multi-service fan-out safety: a negative attribution control

Status 2026-11-17: deterministic **synthetic** multi-service test graphs,
not production traces, and not a measured live distributed deployment.

Span exclusive time is calculated by subtracting the union of child intervals.
This is correct for local-clock span accounting, but summing exclusive time
over parallel branches does not identify the end-to-end request critical path.
A slow branch may be hidden behind another parallel branch. A regression
screen that always names the largest exclusive-time increase can therefore
appear confident without actually identifying the wall-time bottleneck.

The comparator now tracks overlapping sibling intervals. When any comparable
trace contains concurrent sibling spans, the comparator returns
insufficient_comparable_evidence with a parallel-span warning, instead of
claiming a single measured contributor. A serial three-service chain still
supports exclusive-time attribution. A child ending exactly as another starts
is not considered overlapping.

Reproduce offline:

    PYTHONPATH=src python3 -m unittest discover -s tests -p test_parallel_fanout.py -v

This conservative rule sacrifices sensitivity on parallel request graphs.
Future work: a carefully defined critical-path analysis, multiple independent
real traces, temporal clock-synchronization provenance and negative controls.
A structural warning is not a discovered root cause.
