"""Generate example collector batches into ./incoming/.

Deterministic for a given --seed, so results can be reproduced.
"""

import argparse
import json
import os
import random
import shutil
from datetime import datetime, timedelta, timezone

COLLECTORS = [f"col-{i:02d}" for i in range(1, 9)]
NOISY_COLLECTOR = "col-03"      # sends most of the traffic
SKEWED_COLLECTOR = "col-07"     # clock is wrong
SKEW = timedelta(hours=5)

DOMAINS = [
    "example.com", "cdn.example.net", "login.acme-corp.com", "updates.vendor.io",
    "telemetry.device-maker.com", "a7f3k2.dyn-dns.ru", "pool.ntp.org",
    "api.payments-gateway.com", "mail.internal.lan", "search.provider.com",
]
VERDICTS = ["allow", "allow", "allow", "block", "monitor"]

BASE = datetime(2024, 9, 18, 12, 0, 0, tzinfo=timezone.utc)


def iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{dt.microsecond // 1000:03d}Z"


def pick_collector(rng):
    if rng.random() < 0.55:
        return NOISY_COLLECTOR
    return rng.choice([c for c in COLLECTORS if c != NOISY_COLLECTOR])


def make_ip(rng):
    return f"10.{rng.randint(0, 40)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def format_ts(rng, event_time):
    """Return the timestamp in one of the formats collectors actually send."""
    roll = rng.random()
    if roll < 0.70:
        return iso_z(event_time)
    if roll < 0.76:
        return event_time.strftime("%Y-%m-%dT%H:%M:%S.") + \
            f"{event_time.microsecond // 1000:03d}"
    if roll < 0.82:
        return event_time.strftime("%Y-%m-%d %H:%M:%S")
    if roll < 0.88:
        return int(event_time.timestamp() * 1000)
    if roll < 0.93:
        return int(event_time.timestamp())
    if roll < 0.96:
        return str(int(event_time.timestamp()))
    # Firmware bug: a device that thinks it is in 2075, seconds precision.
    return int(event_time.replace(year=2075).timestamp())


def base_record(rng, event_time, received_at, collector=None, ip=None):
    collector = collector or pick_collector(rng)
    if collector == SKEWED_COLLECTOR:
        event_time = event_time + SKEW
    return {
        "ts": format_ts(rng, event_time),
        "collector_id": collector,
        "client_ip": ip or make_ip(rng),
        "query": rng.choice(DOMAINS),
        "verdict": rng.choice(VERDICTS),
        "received_at": iso_z(received_at),
    }


def build_batches(rng, total_records, num_files):
    """Return a list of batches; each batch is a list of raw lines (strings)."""
    per_file = max(1, total_records // num_files)
    batches = []
    clock = BASE
    retry_pool = []

    for file_index in range(num_files):
        lines = []
        # A collector that lost its connection resends a whole batch later.
        # Those resent records land in a DIFFERENT file than the original.
        if retry_pool and rng.random() < 0.5:
            for original in retry_pool:
                resent = dict(original)
                resent["received_at"] = iso_z(clock + timedelta(seconds=rng.randint(3, 20)))
                lines.append(json.dumps(resent))
            retry_pool = []

        while len(lines) < per_file:
            clock = clock + timedelta(milliseconds=rng.randint(1, 60))
            roll = rng.random()
            record = base_record(rng, clock, clock + timedelta(milliseconds=rng.randint(20, 900)))

            if roll < 0.03:
                # A device really did the same thing twice in the same second.
                # Same file, so it is not a network retry.
                lines.append(json.dumps(record))
                twin = dict(record)
                twin["received_at"] = iso_z(clock + timedelta(milliseconds=rng.randint(20, 900)))
                lines.append(json.dumps(twin))
                continue

            if roll < 0.07:
                del record["client_ip"]
                lines.append(json.dumps(record))
                continue

            if roll < 0.09:
                record["client_ip"] = rng.choice(["10.300.1.5", "not-an-ip", "10.1.1"])
                lines.append(json.dumps(record))
                continue

            if roll < 0.12:
                broken = json.dumps(record)
                cut = rng.randint(10, max(11, len(broken) - 10))
                lines.append(broken[:cut])
                continue

            lines.append(json.dumps(record))
            if len(retry_pool) < 30 and rng.random() < 0.09:
                retry_pool.append(record)

        batches.append(lines)

    # Two files end with a line that was cut in half mid-write.
    for target in (2, num_files // 2):
        if 0 <= target < len(batches) and batches[target]:
            last = batches[target][-1]
            batches[target][-1] = last[: max(5, len(last) // 2)]

    return batches


def write(batches, directory):
    if os.path.isdir(directory):
        shutil.rmtree(directory)
    os.makedirs(directory)
    for index, lines in enumerate(batches):
        path = os.path.join(directory, f"batch-{index:04d}.ndjson")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
            handle.write("\n")
    return len(batches)


def main():
    parser = argparse.ArgumentParser(description="generate example collector data")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--large", action="store_true", help="about 1.2M records")
    parser.add_argument("--out", default="./incoming")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    if args.large:
        total, files = 1_200_000, 300
    else:
        total, files = 5_000, 12

    batches = build_batches(rng, total, files)
    count = write(batches, args.out)
    written = sum(len(b) for b in batches)
    print(f"wrote {written} lines across {count} files in {args.out} (seed {args.seed})")


if __name__ == "__main__":
    main()
