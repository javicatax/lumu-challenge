"""Count how many collapses are retries vs legitimate twins.

Run from anywhere:
    python3 scripts/script_analyze_collapses.py [directory]

Defaults to ./incoming.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# Make the repo root importable regardless of the current working directory.
# The script lives in scripts/, so the repo root is one level up.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from intake.normalize import normalize
from intake.summary import fingerprint_function

# Threshold (seconds) to classify a pair as retry vs legitimate twin.
# Generator values: retries have a gap of 3-20 s; twins of 0.02-0.9 s.
# We use 1.0 s as the boundary: everything above is a retry, everything
# below is a twin. The gap between 1 and 3 seconds is empty in the data.
RETRY_GAP_SECONDS = 1.0


def _parse_iso(ts):
    return datetime.fromisoformat(ts)


def analyze(directory):
    by_fp = defaultdict(list)

    for name in sorted(os.listdir(directory)):
        if not name.endswith(".ndjson"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record, reason = normalize(raw)
                if reason is not None:
                    continue
                by_fp[fingerprint_function(record)].append(record)

    total_groups = 0
    retries = 0
    twins = 0

    for records in by_fp.values():
        if len(records) < 2:
            continue
        total_groups += 1

        # Sort by received_at to compare gaps in order.
        records = [r for r in records if r["received_at"]]
        records.sort(key=lambda r: r["received_at"])
        if not records:
            continue

        first_received = _parse_iso(records[0]["received_at"])
        for r in records[1:]:
            gap = (_parse_iso(r["received_at"]) - first_received).total_seconds()
            if gap > RETRY_GAP_SECONDS:
                retries += 1
            else:
                twins += 1

    print(f"Groups with >1 record: {total_groups}")
    print(f"Likely retries (gap > {RETRY_GAP_SECONDS}s): {retries}")
    print(f"Likely twins (gap <= {RETRY_GAP_SECONDS}s): {twins}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "./incoming"
    analyze(target)