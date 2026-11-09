"""Regression cases for shape-comparison blind spots with same-named spans."""
from dataclasses import dataclass
import unittest
from traceroot.topology import canonical_topology


@dataclass(frozen=True)
class Node:
    span_id: str
    service: str
    parent: str | None = None
    operation: str | None = 'work'


def graph(assignment='split'):
    # Same service/parent-service edge multiset in both cases, but different
    # trees: two workers have one dependency each, versus two on one worker.
    nodes = [Node('root','api',None),
             Node('a','worker','root'), Node('b','worker','root'),
             Node('db','db','a'),
             Node('cache','cache','b' if assignment=='split' else 'a')]
    return {n.span_id:n for n in nodes}


class StructuralFingerprintTests(unittest.TestCase):
    def test_detects_redistributed_child_with_same_service_edge_multiset(self):
        a,b = graph('split'),graph('merged')
        def flat(nodes):
            return sorted((n.service, nodes[n.parent].service if n.parent else '')
                          for n in nodes.values())
        self.assertEqual(flat(a),flat(b))  # The previous implementation is blind.
        self.assertNotEqual(canonical_topology(a),canonical_topology(b))

    def test_identifiers_and_insertion_order_do_not_affect_structure(self):
        a=graph()
        mapping={s:f'x{i}' for i,s in enumerate(reversed(list(a)))}
        reordered={mapping[k]:Node(mapping[k],n.service,
                    mapping[n.parent] if n.parent else None,n.operation)
                   for k,n in reversed(list(a.items()))}
        self.assertEqual(canonical_topology(a),canonical_topology(reordered))

    def test_sibling_order_does_not_affect_structure(self):
        a=graph()
        self.assertEqual(canonical_topology(a),canonical_topology(dict(reversed(list(a.items())))))

    def test_operation_change_is_structural_change(self):
        a=graph()
        b=dict(a)
        b['db']=Node('db','db','a','read_v2')
        self.assertNotEqual(canonical_topology(a),canonical_topology(b))

    def test_missing_parent_rejected(self):
        with self.assertRaisesRegex(ValueError,'orphaned'):
            canonical_topology({'a':Node('a','db','missing')})

    def test_cycle_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing root'):
            canonical_topology({'a':Node('a','db','b'),'b':Node('b','db','a')})

    def test_disconnected_cycle_rejected(self):
        d={'root':Node('root','api'), 'a':Node('a','db','b'),'b':Node('b','db','a')}
        with self.assertRaisesRegex(ValueError,'unreachable'):
            canonical_topology(d)

    def test_mismatched_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,'span key'):
            canonical_topology({'fake':Node('real','api')})

    def test_multiple_roots_deterministic(self):
        d={'b':Node('b','api'), 'a':Node('a','worker')}
        self.assertEqual(canonical_topology(d),canonical_topology(dict(reversed(list(d.items())))))


if __name__=='__main__': unittest.main()
