"""Read collector batch files and print a summary.

Two execution paths:

- workers=1: sequential.
- workers>1: ProcessPoolExecutor. Each file is processed independently by
  a worker
We use round-robin sharding (implicit in
pool.map), not sharding by collector.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter

from intake.normalize import normalize
from intake.summary import Summary

DEFAULT_DIR = "./incoming"


def batch_files(directory, shuffle=False):
    """Return the list of .ndjson files to process.
    This does NOT affect the summary output: all counters in Summary are
    commutative, so any order produces the same result.
    With shuffle=True, the order is randomized with a fixed seed. Used
    only to verify order-independence in tests.
    """
    names = [n for n in os.listdir(directory) if n.endswith(".ndjson")]
    names.sort()
    if shuffle:
        import random
        random.Random(0).shuffle(names)
    return [os.path.join(directory, n) for n in names]


def read_batch(path):
    """Yield (raw, reason) pairs.
    """
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                yield None, "malformed_line"
                continue
            if not isinstance(parsed, dict):
                yield None, "not_a_dict"
                continue
            yield parsed, None

def _process_file(path):
    """Process one file. Returns (partial_summary, partial_rejections).
    """
    partial = Summary()
    rejections = Counter()

    for raw, reason in read_batch(path):
        if reason is not None:
            rejections[reason] += 1
            continue
        record, reason = normalize(raw)
        if reason is not None:
            rejections[reason] += 1
            continue
        partial.add(record)

    return partial, rejections

def run_sequential(directory, shuffle=False):
    """Sequential reference implementation.
    """
    summary = Summary()
    rejections = Counter()

    for path in batch_files(directory, shuffle=shuffle):
        partial, partial_rejections = _process_file(path)
        summary.merge(partial)
        rejections.update(partial_rejections)

    return summary, rejections

def run_parallel(directory, workers, shuffle=False):
    """Parallel implementation using a process pool.
    Each file is processed independently by a worker. Partial summaries
    and rejection counters are merged into the final result.
    The merge operation is commutative
    """
    from concurrent.futures import ProcessPoolExecutor

    paths = batch_files(directory, shuffle=shuffle)

    summary = Summary()
    rejections = Counter()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        for partial, partial_rejections in pool.map(_process_file, paths):
            summary.merge(partial)
            rejections.update(partial_rejections)

    return summary, rejections


def run(directory, workers=1, shuffle=False):
    """Dispatch to the sequential or parallel path based on workers.
    workers=1 is deliberately routed to a separate function, not to
    run_parallel(workers=1).
    """
    if workers <= 1:
        return run_sequential(directory, shuffle=shuffle)
    return run_parallel(directory, workers=workers, shuffle=shuffle)

def render_rejections(rejections):
    """Render the rejection Counter as a small block for the summary."""
    if not rejections:
        return ""
    lines = ["Rejections"]
    for reason in sorted(rejections):
        lines.append(f"  {reason}: {rejections[reason]}")
    return "\n".join(lines)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Lumu intake service")
    parser.add_argument("--dir", default=DEFAULT_DIR,
                        help="directory with batch files")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of worker processes (default: 1)")
    parser.add_argument("--shuffle", action="store_true",
                        help="process files in randomized order "
                             "(for verification only)")
    parser.add_argument("--timing", action="store_true",
                        help="print elapsed time to stderr")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        print(f"no such directory: {args.dir}", file=sys.stderr)
        return 1
    if args.workers < 1:
        print(f"--workers must be >= 1, got {args.workers}", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    summary, rejections = run(args.dir, workers=args.workers,
                              shuffle=args.shuffle)
    t1 = time.perf_counter()

    print(summary.render())

    rejection_text = render_rejections(rejections)
    if rejection_text:
        print()
        print(rejection_text)

    if args.timing:
        print(f"\nelapsed: {t1 - t0:.3f}s (workers={args.workers})",
              file=sys.stderr)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())