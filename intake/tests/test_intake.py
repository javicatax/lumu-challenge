"""Tests for the intake service."""

import unittest

from intake.normalize import normalize, parse_timestamp
from intake.summary import Summary


class TestParseTimestamp(unittest.TestCase):
    def test_iso_with_z(self):
        self.assertEqual(
            parse_timestamp("2021-12-03T16:15:30.235Z").isoformat(),
            "2021-12-03T16:15:30.235000+00:00",
        )

    def test_iso_without_zone(self):
        self.assertEqual(
            parse_timestamp("2011-12-03T10:15:30").isoformat(),
            "2011-12-03T10:15:30+00:00",
        )

    def test_space_separator(self):
        self.assertEqual(
            parse_timestamp("2021-12-03 16:15:30").isoformat(),
            "2021-12-03T16:15:30+00:00",
        )

    def test_epoch_millis(self):
        self.assertEqual(
            parse_timestamp(1726668850124).isoformat(),
            "2024-09-18T14:14:10.124000+00:00",
        )

    def test_epoch_seconds(self):
        self.assertEqual(
            parse_timestamp(1726667942).isoformat(),
            "2024-09-18T13:59:02+00:00",
        )

    def test_epoch_seconds_as_string(self):
        self.assertEqual(
            parse_timestamp("1726667942").isoformat(),
            "2024-09-18T13:59:02+00:00",
        )


class TestNormalize(unittest.TestCase):
    def sample(self):
        return {
            "ts": "2024-09-18T12:00:00.000Z",
            "collector_id": "col-01",
            "client_ip": "10.1.2.3",
            "query": "Example.COM",
            "verdict": "allow",
            "received_at": "2024-09-18T12:00:01.000Z",
        }

    def test_normalizes_a_good_record(self):
        record = normalize(self.sample())
        self.assertEqual(record["collector_id"], "col-01")
        self.assertEqual(record["query"], "example.com")
        self.assertEqual(record["event_time"], "2024-09-18T12:00:00+00:00")

    def test_missing_field_is_rejected(self):
        raw = self.sample()
        del raw["client_ip"]
        self.assertIsNone(normalize(raw))

    def test_bad_timestamp_is_rejected(self):
        raw = self.sample()
        raw["ts"] = "not a date"
        self.assertIsNone(normalize(raw))


class TestSummary(unittest.TestCase):
    def record(self, ip="10.1.2.3", received="2024-09-18T12:00:01.000Z"):
        return {
            "event_time": "2024-09-18T12:00:00+00:00",
            "received_at": received,
            "collector_id": "col-01",
            "client_ip": ip,
            "query": "example.com",
            "verdict": "allow",
        }

    def test_counts_one_record(self):
        summary = Summary()
        summary.add(self.record())
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.by_verdict["allow"], 1)
        self.assertEqual(len(summary.unique_ips), 1)

    def test_counts_two_different_ips(self):
        summary = Summary()
        summary.add(self.record(ip="10.1.2.3"))
        summary.add(self.record(ip="10.1.2.4"))
        self.assertEqual(summary.processed, 2)
        self.assertEqual(len(summary.unique_ips), 2)

    def test_identical_records_are_one_event(self):
        summary = Summary()
        summary.add(self.record())
        summary.add(self.record())
        self.assertEqual(len(summary.unique_events), 1)

    def test_render_includes_totals(self):
        summary = Summary()
        summary.add(self.record())
        text = summary.render()
        self.assertIn("records processed: 1", text)
        self.assertIn("unique client IPs: 1", text)


if __name__ == "__main__":
    unittest.main()
