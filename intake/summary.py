"""Aggregate counters for the intake service."""

import hashlib
import json

MISSING = "(missing)"

def _looks_like_ipv4(text):
    """Strict IPv4 validation.
      - require the value to be a string
      - require ASCII digits only
      - reject leading zeros
      - enforce 0..255 per octet
    """
    if not isinstance(text, str):
        return False
    parts = text.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isascii() or not part.isdigit():
            return False
        if len(part) > 1 and part[0] == "0":
            return False  # no leading zeros
        if not 0 <= int(part) <= 255:
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

        # --- Unique IPs: only syntactically valid IPv4 ---
        client_ip = record.get("client_ip")
        if client_ip is None:
            self.missing_client_ip += 1
        elif _looks_like_ipv4(client_ip):
            self.unique_ips.add(client_ip)
        else:
            self.invalid_ips += 1

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

    def merge(self, other):
        """Merge another Summary into this one and return self.

        Every operation here is commutative:
          - counters: sum
          - dict counters: sum per key
          - sets: union

        Therefore, the result is independent of merge order.
        """
        self.processed += other.processed

        for key, value in other.by_verdict.items():
            self.by_verdict[key] = self.by_verdict.get(key, 0) + value

        for key, value in other.by_collector.items():
            self.by_collector[key] = self.by_collector.get(key, 0) + value

        self.unique_events |= other.unique_events
        self.unique_ips |= other.unique_ips

        self.invalid_ips += other.invalid_ips
        self.missing_client_ip += other.missing_client_ip
        self.missing_query += other.missing_query
        self.missing_verdict += other.missing_verdict
        self.clock_suspect += other.clock_suspect
        self.missing_received_at += other.missing_received_at

        return self

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
        lines.append("")

        lines.append("By collector")
        for collector in sorted(self.by_collector):
            lines.append(f"  {collector}: {self.by_collector[collector]}")

        return "\n".join(lines)
