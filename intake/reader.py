"""Read collector batch files and print a summary."""

import argparse
import json
import os
import sys

from intake.normalize import normalize
from intake.summary import Summary

DEFAULT_DIR = "./incoming"


def batch_files(directory):
    names = [n for n in os.listdir(directory) if n.endswith(".ndjson")]
    return [os.path.join(directory, n) for n in sorted(names)]


def read_batch(path):
    """Generator: returns Yield (raw, reason) pairs."""
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

def run(directory):
    summary = Summary()
    for path in batch_files(directory):
        for raw in read_batch(path):
            record = normalize(raw)
            if record is None:
                continue
            summary.add(record)
    return summary

def main(argv=None):
    parser = argparse.ArgumentParser(description="Lumu intake service")
    parser.add_argument("--dir", default=DEFAULT_DIR, help="directory with batch files")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        print(f"no such directory: {args.dir}", file=sys.stderr)
        return 1

    summary = run(args.dir)
    print(summary.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
