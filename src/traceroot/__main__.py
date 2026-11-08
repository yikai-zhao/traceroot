"""Offline CLI; never executes external tools or network calls."""
import argparse
import json
from pathlib import Path
from .core import read_events, run
from .traces import compare_runs


def main():
    parser = argparse.ArgumentParser(description='TraceRoot evidence-first offline analysis')
    parser.add_argument('events', nargs='?', type=Path,
                        help='normalized event JSONL file for observation report')
    parser.add_argument('--compare', nargs=2, type=Path,
                        metavar=('BASELINE_JSONL', 'CANDIDATE_JSONL'),
                        help='compare repeated traces of the same operation')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if bool(args.events) == bool(args.compare):
        parser.error('choose an event file or --compare BASELINE CANDIDATE')
    if args.compare:
        left, left_sha = read_events(args.compare[0])
        right, right_sha = read_events(args.compare[1])
        report = compare_runs(left, right)
        report['source_sha256'] = {'baseline': left_sha, 'candidate': right_sha}
    else:
        report = run(args.events)
    message = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(message)
    else:
        print(message, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
