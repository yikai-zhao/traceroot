# Comparable call trees, not just matching service names

The existing regression analyzer measures a service's **exclusive span time**
(parent inclusive time minus the union of direct child intervals). Its output is
only meaningful when baseline/candidate request structures are comparable.

## An adversarial false comparison

Consider two request graphs, both with an `api` root, two separate `worker`
spans, and one `db` and one `cache` dependency.

- Baseline: worker A → db; worker B → cache.
- Candidate: worker A → db **and** cache; worker B → no child.

Both have the same multiset of `(service, parent_service)` edges. Flat tuple
comparison therefore cannot tell them apart and might attribute a time delta
to the wrong service. Their **rooted trees are not isomorphic**.

`canonical_topology` constructs a sorted recursive signature for each root,
with service and operation at each node. It ignores unstable span IDs and
sibling recording order, preserves multiplicity and complete descendant
structure, and rejects orphaned/cyclic graphs. `compare_runs` now uses this
signature before computing deltas; incomparable structures result in
`insufficient_comparable_evidence`, not a fabricated regression explanation.

The test suite exercises the explicit counterexample, ID invariance, order
invariance, changed operation, missing parents, cycles and duplicate-key errors.

## Limits

- This is **structural** equivalence, not evidence that CPU contention,
  sampling, downstream resource limits or clock conditions are matched.
- Only one shared host's monotonic clock domain is supported. Cross-host traces
  need clock treatment and instrumentation not supplied here.
- Even with identical topology, the largest exclusive-time contributor is a
  **measured investigation target**, not proof of underlying root cause.
- A genuinely added retry changes topology and triggers abstention. This is
  conservative by design, not a classification of the retry as a defect.
