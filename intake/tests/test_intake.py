"""Tests for the intake service."""

import unittest
from datetime import datetime, timezone

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

    def test_bool_is_rejected(self):
        """A boolean is not a timestamp, even though bool is a subclass of int."""
        with self.assertRaises(TypeError):
            parse_timestamp(True)

    def test_epoch_year_2075_is_not_rejected(self):
        """A device with a clock set to 2075 must not be rejected outright.

        This is the case generate.py produces via the firmware bug:
        event_time.replace(year=2075). The record must survive parsing so
        that clock_suspect can flag it downstream, rather than being
        discarded at the parsing step.
        """
        ts = int(datetime(2075, 9, 18, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        result = parse_timestamp(ts)
        self.assertEqual(result.year, 2075)


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
        record, reason = normalize(self.sample())
        self.assertIsNone(reason)
        self.assertEqual(record["collector_id"], "col-01")
        self.assertEqual(record["query"], "example.com")
        self.assertEqual(record["event_time"], "2024-09-18T12:00:00+00:00")
        self.assertFalse(record["clock_suspect"])

    def test_missing_identity_field_rejects_with_reason(self):
        raw = self.sample()
        del raw["ts"]
        record, reason = normalize(raw)
        self.assertIsNone(record)
        self.assertEqual(reason, "missing_ts")

    def test_missing_attribute_field_is_accepted_with_none(self):
        raw = self.sample()
        del raw["client_ip"]
        record, reason = normalize(raw)
        self.assertIsNone(reason)
        self.assertIsNotNone(record)
        self.assertIsNone(record["client_ip"])

    def test_bad_timestamp_is_rejected(self):
        raw = self.sample()
        raw["ts"] = "not a date"
        record, reason = normalize(raw)
        self.assertIsNone(record)
        self.assertEqual(reason, "bad_timestamp")

    def test_future_timestamp_is_flagged(self):
        """A ts in 2075 is flagged clock_suspect but not rejected.

        The record keeps the original event_time. Downstream must use
        received_at when clock_suspect is True.
        """
        raw = self.sample()
        raw["ts"] = "2075-09-18T12:00:00.000Z"
        record, reason = normalize(raw)
        self.assertIsNone(reason)
        self.assertTrue(record["clock_suspect"])
        self.assertEqual(record["event_time"], "2075-09-18T12:00:00+00:00")

    def test_null_collector_id_is_rejected(self):
        raw = self.sample()
        raw["collector_id"] = None
        record, reason = normalize(raw)
        self.assertIsNone(record)
        self.assertEqual(reason, "bad_collector_id")


class TestSummary(unittest.TestCase):
    def record(self, ip="10.1.2.3",
               received="2024-09-18T12:00:01.000Z",
               verdict="allow",
               clock_suspect=False):
        return {
            "event_time": "2024-09-18T12:00:00+00:00",
            "received_at": received,
            "collector_id": "col-01",
            "client_ip": ip,
            "query": "example.com",
            "verdict": verdict,
            "clock_suspect": clock_suspect,
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

    def test_invariant_by_verdict_equals_processed(self):
        summary = Summary()
        summary.add(self.record(ip="not-an-ip"))
        summary.add(self.record(ip="10.300.1.5"))
        self.assertEqual(summary.processed, 2)
        self.assertEqual(sum(summary.by_verdict.values()), 2)

    def test_retry_with_different_received_at_is_one_event(self):
        summary = Summary()
        summary.add(self.record(received="2024-09-18T12:00:01.000Z"))
        summary.add(self.record(received="2024-09-18T12:05:30.000Z"))
        self.assertEqual(summary.processed, 2)
        self.assertEqual(len(summary.unique_events), 1)

    def test_unique_ips_does_not_include_invalid(self):
        summary = Summary()
        summary.add(self.record(ip="not-an-ip"))
        self.assertEqual(len(summary.unique_ips), 0)
        self.assertEqual(summary.invalid_ips, 1)

    def test_unique_ips_does_not_include_none(self):
        """A record with client_ip=None must not pollute unique_ips.

        This covers the double .add() bug: None was being inserted into
        the set alongside missing_client_ip being incremented.
        """
        summary = Summary()
        summary.add(self.record(ip=None))
        self.assertNotIn(None, summary.unique_ips)
        self.assertEqual(len(summary.unique_ips), 0)
        self.assertEqual(summary.missing_client_ip, 1)

    def test_unique_events_includes_records_with_invalid_ip(self):
        summary = Summary()
        summary.add(self.record(ip="not-an-ip"))
        self.assertEqual(summary.processed, 1)
        self.assertEqual(len(summary.unique_events), 1)

    def test_missing_verdict_is_categorized(self):
        from intake.summary import MISSING
        summary = Summary()
        summary.add(self.record(verdict=None))
        self.assertEqual(summary.by_verdict[MISSING], 1)
        self.assertEqual(summary.missing_verdict, 1)
        self.assertEqual(sum(summary.by_verdict.values()), 1)

    def test_clock_suspect_is_counted(self):
        summary = Summary()
        summary.add(self.record(clock_suspect=True))
        self.assertEqual(summary.clock_suspect, 1)

    def test_render_includes_totals(self):
        summary = Summary()
        summary.add(self.record())
        text = summary.render()
        normalized = " ".join(text.split())
        self.assertIn("records processed: 1", normalized)
        self.assertIn("unique client IPs: 1", normalized)


if __name__ == "__main__":
    unittest.main()