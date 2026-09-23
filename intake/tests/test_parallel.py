"""Test parallel processing

- Summary.merge is commutative.
- _process_file is pure.
- run(directory, workers=N) produces the same output for any N.
- run(directory, shuffle=True) produces the same output as without shuffle.
"""

import json
import os
import shutil
import tempfile
import unittest

from intake.reader import run, _process_file
from intake.summary import Summary


def _make_record(event_time, collector_id, client_ip, query, verdict,
                 received_at="2024-09-18T12:00:01.000Z"):
    return {
        "ts": event_time,
        "collector_id": collector_id,
        "client_ip": client_ip,
        "query": query,
        "verdict": verdict,
        "received_at": received_at,
    }

class TestParallelInvariance(unittest.TestCase):
    """The output must be identical across worker counts and file orders."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        # Build a small deterministic dataset distributed across 12 files.
        base_events = []
        for i in range(200):
            base_events.append(_make_record(
                event_time=f"2024-09-18T12:00:{i % 60:02d}.000Z",
                collector_id=f"col-{i % 4:02d}",
                client_ip=f"10.1.2.{i % 30}",
                query=f"q{i % 10}.com",
                verdict=("allow", "block", "monitor")[i % 3],
            ))
        num_files = 12
        for file_index in range(num_files):
            path = os.path.join(cls.tmp, f"batch-{file_index:04d}.ndjson")
            with open(path, "w", encoding="utf-8") as f:
                for j in range(file_index, len(base_events), num_files):
                    f.write(json.dumps(base_events[j]) + "\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_same_output_1_vs_8_workers(self):
        s1, r1 = run(self.tmp, workers=1)
        s8, r8 = run(self.tmp, workers=8)
        self.assertEqual(s1.render(), s8.render())
        self.assertEqual(r1, r8)

    def test_same_output_shuffled(self):
        s1, r1 = run(self.tmp, workers=1, shuffle=False)
        s2, r2 = run(self.tmp, workers=1, shuffle=True)
        self.assertEqual(s1.render(), s2.render())
        self.assertEqual(r1, r2)

    def test_same_output_8_workers_shuffled(self):
        s1, _ = run(self.tmp, workers=1, shuffle=False)
        s8, _ = run(self.tmp, workers=8, shuffle=True)
        self.assertEqual(s1.render(), s8.render())

    def test_rejections_are_merged_correctly(self):
        # Add a file with a malformed line and one missing identity field.
        path = os.path.join(self.tmp, "batch-9999.ndjson")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json\n")
            f.write('{"ts": "2024-09-18T12:00:00Z", '
                    '"collector_id": "col-01"}\n')  # missing attrs is OK
            f.write('{"ts": "not-a-date", "collector_id": "col-01", '
                    '"client_ip": "10.1.2.3", "query": "x", '
                    '"verdict": "allow"}\n')
        try:
            _, r1 = run(self.tmp, workers=1)
            _, r8 = run(self.tmp, workers=8)
            self.assertEqual(r1, r8)
        finally:
            os.unlink(path)


class TestMergeIsCommutative(unittest.TestCase):
    def test_merge_is_commutative(self):
        # Two disjoint sets of records.
        a = Summary()
        for i in range(20):
            a.add({
                "event_time": "2024-09-18T12:00:00+00:00",
                "received_at": "2024-09-18T12:00:01+00:00",
                "collector_id": f"col-A-{i}",
                "client_ip": f"10.1.1.{i}",
                "query": f"a{i}.com",
                "verdict": "allow",
                "clock_suspect": False,
            })
        b = Summary()
        for i in range(20):
            b.add({
                "event_time": "2024-09-18T12:00:00+00:00",
                "received_at": "2024-09-18T12:00:01+00:00",
                "collector_id": f"col-B-{i}",
                "client_ip": f"10.2.2.{i}",
                "query": f"b{i}.com",
                "verdict": "block",
                "clock_suspect": False,
            })

        left = Summary().merge(a).merge(b).render()
        right = Summary().merge(b).merge(a).render()
        self.assertEqual(left, right)

class TestProcessFileIsPure(unittest.TestCase):
    def test_process_file_same_result_regardless_of_order(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "batch-0000.ndjson")
        with open(path, "w", encoding="utf-8") as f:
            for i in range(50):
                f.write(json.dumps(_make_record(
                    event_time=f"2024-09-18T12:00:{i % 60:02d}.000Z",
                    collector_id="col-01",
                    client_ip=f"10.1.2.{i}",
                    query=f"q{i}.com",
                    verdict="allow",
                )) + "\n")

        s1, r1 = _process_file(path)
        s2, r2 = _process_file(path)
        self.assertEqual(s1.render(), s2.render())
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()