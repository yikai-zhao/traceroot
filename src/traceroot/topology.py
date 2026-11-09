"""Canonical rooted call-tree fingerprint; ignores nonsemantic span identifiers.

A flat list of (service, parent_service) edges cannot distinguish two equally
named parent spans from a single parent having both children. Recursive tree
structure can. This module is deliberately independent of tracing frameworks.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Protocol


class SpanNode(Protocol):
    span_id: str
    service: str
    operation: str | None
    parent: str | None


def canonical_topology(nodes: Mapping[str, SpanNode]) -> tuple:
    """Return an ID-independent, sibling-order-independent call-tree signature.

    Non-isomorphic trees must not be compared for exclusive-time attribution:
    missing retries or moved dependencies change the timing decomposition.
    """
    children: dict[str, list[str]] = defaultdict(list)
    roots = []
    for key, node in nodes.items():
        if key != node.span_id:
            raise ValueError('span key does not match span ID')
        if node.parent is None:
            roots.append(key)
        else:
            if node.parent not in nodes:
                raise ValueError('orphaned span in call tree')
            children[node.parent].append(key)
    if not roots:
        raise ValueError('call tree missing root')

    active = set()
    visited = set()

    def visit(key: str) -> tuple:
        if key in active:
            raise ValueError('cyclic call tree')
        if key in visited:
            raise ValueError('span referenced by multiple parents')
        active.add(key)
        node = nodes[key]
        branches = tuple(sorted(visit(child) for child in children[key]))
        active.remove(key)
        visited.add(key)
        return (node.service, node.operation or '', branches)

    shape = tuple(sorted(visit(root) for root in roots))
    if len(visited) != len(nodes):
        raise ValueError('unreachable spans or cycle in call graph')
    return shape
