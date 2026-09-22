"""Aggregate counters for the intake service."""

import hashlib
import json

MISSING = "(missing)"


def _looks_like_ipv4(text):
    parts = text.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            return False
    return True

def fingerprint_function(record):
    """General fingerprint function to validating unique records"""

    # Exclude 'received_at' field (If include it - All records will be different)
    payload = {
        "collector_id": record["collector_id"],
        "event_time": record["event_time"],
        "client_ip": record["client_ip"],
        "query": record["query"],
        "verdict": record["verdict"],
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


class Summary:
    def __init__(self):
        self.processed = 0
        self.by_verdict = {}
        self.unique_events = set()
        self.unique_ips = set()
        self.by_collector = {}
        # --- Quality flags: Define Validate and categorize row ---
        self.invalid_ips = 0  # accepted records whose client_ip is not valid IPv4
        self.missing_client_ip = 0  # accepted records with client_ip = None
        self.missing_query = 0  # accepted records with query = None
        self.missing_verdict = 0  # accepted records with verdict = None
        self.clock_suspect = 0  # accepted records flagged by normalize()
        self.missing_received_at = 0  # accepted records with received_at = None

    def add(self, record):
        # All lines no exception are counting
        self.processed += 1

        verdict = record.get("verdict")
        verdict_key = verdict if verdict is not None else MISSING
        self.by_verdict[verdict_key] = self.by_verdict.get(verdict_key, 0) + 1

        collector = record["collector_id"]
        self.by_collector[collector] = self.by_collector.get(collector, 0) + 1

        if not _looks_like_ipv4(record["client_ip"]):
            return

        self.unique_events.add(fingerprint_function(record))

        # Quality flags: Define Validate and categorize row
        if verdict is None:
            self.missing_verdict += 1
        if record.get("query") is None:
            self.missing_query += 1
        if record.get("received_at") is None:
            self.missing_received_at += 1
        if record.get("clock_suspect"):
            self.clock_suspect += 1

        self.unique_ips.add(record["client_ip"])

    def render(self):
        lines = []
        lines.append("=== intake summary ===")
        lines.append("")

        lines.append("Volume")
        lines.append(f"  records processed:       {self.processed}")
        lines.append(f"  unique events:           {len(self.unique_events)}")
        lines.append(f"  unique client IPs:       {len(self.unique_ips)}")
        lines.append("")

        lines.append("Quality flags")
        lines.append(f"  invalid client_ip:       {self.invalid_ips}")
        lines.append(f"  missing client_ip:       {self.missing_client_ip}")
        lines.append(f"  missing query:           {self.missing_query}")
        lines.append(f"  missing verdict:         {self.missing_verdict}")
        lines.append(f"  missing received_at:     {self.missing_received_at}")
        lines.append(f"  clock suspect:           {self.clock_suspect}")
        lines.append("")

        lines.append("By verdict")

        for verdict in sorted(self.by_verdict):
            lines.append(f"  {verdict}: {self.by_verdict[verdict]}")
        lines.append("by collector:")
        for collector in sorted(self.by_collector):
            lines.append(f"  {collector}: {self.by_collector[collector]}")

        return "\n".join(lines)
