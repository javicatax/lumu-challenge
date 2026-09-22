# intake

A small service that reads collector batch files, normalizes each record, and prints a
summary.

Python 3.9 or newer. Standard library only — no packages to install.

## Generate example data

```bash
python3 generate.py
```

This writes about 5,000 records across 12 files into `./incoming/`.

The generator is deterministic. The same `--seed` always produces the same data, so your
results can be reproduced:

```bash
python3 generate.py --seed 99
```

For the large data set (about 1.2 million records across 300 files, roughly 200 MB on disk):

```bash
python3 generate.py --large --out ./incoming_large
```

## Run the service

```bash
python3 -m intake.reader
```

Or point it at another directory:

```bash
python3 -m intake.reader --dir ./incoming_large
```

## Run the tests

```bash
python3 -m unittest discover -s intake/tests -t . -v
```

## Files

| File | What it does |
| --- | --- |
| `intake/reader.py` | Finds the batch files, reads each line, prints the summary |
| `intake/normalize.py` | Turns one raw record into a normalized record |
| `intake/summary.py` | Keeps the counters and renders the summary text |
| `intake/tests/` | Tests |
| `generate.py` | Creates example collector data |

## Record format

Collectors send one JSON object per line:

```json
{
  "ts": "2024-09-18T12:00:00.000Z",
  "collector_id": "col-01",
  "client_ip": "10.1.2.3",
  "query": "example.com",
  "verdict": "allow",
  "received_at": "2024-09-18T12:00:01.000Z"
}
```

`ts` is the time from the device. `received_at` is the time we received the record.

Not every collector sends `ts` in the same format. Firmware versions differ.
