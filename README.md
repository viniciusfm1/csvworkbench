# csvbench

csvbench is a Python library for reading, diagnosing, and repairing malformed CSV files.
It is under active development and not yet production-ready.

It does not use Python's `csv` module: handling broken files is the point.

---

## Status

Early stage. The core pipeline (encoding detection, parsing, diagnosis) works.
Repair strategies are under active development.

Battle-tested in production? Probably not. But you're welcome to try and to contribute.

---

## Features

- Automatic detection of encoding, delimiter, and quote character
- Multi-character separator support (e.g. `||`, `@@@`)
- Structured diagnostic reports with per-row issue tracking
- Pluggable repair strategies via the Strategy pattern
- CLI with rich terminal output and JSON output for programmatic use

---

## Installation

```bash
pip install csvbench
```

Requires Python 3.11+.

---

## Usage

### CLI

```bash
csvbench inspect appointments.csv
```

```
╭────────────────────────────── csvbench inspect ────────────────────────────────╮
│                                                                                │
│   📁 File  ~/data/appointments.csv                                             │
│   🔤 Encoding  utf-8-sig  (100% confidence - bom)                              │
│   🔀 Separator  ';'  (98% confidence - sniffed)                                │
│   💬 Quotechar  '"'  (97% confidence - detected)                               │
│   📊 Columns  12                                                               │
│   📈 Lines  19847                                                              │
│   ❌ Errors  0                                                                 │
│   ⚠️  Warnings  0                                                              │
│   ⏱️  Elapsed  0.0013s                                                         │
│                                                                                │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✔  No issues found.
```

JSON output for scripting:

```bash
csvbench inspect appointments.csv --format json
csvbench inspect appointments.csv --format json --output report.json
```

Reading from stdin:

```bash
cat appointments.csv | csvbench inspect -
```

### Python API

```python
from csvbench import CsvWorkbench

workbench = CsvWorkbench()
csv_file = workbench.read("appointments.csv")

print(csv_file.delimiter)           # ';'
print(csv_file.encoding)            # 'utf-8-sig'
print(csv_file.report.has_errors)   # False
```

Override detection when you already know the parameters:

```python
csv_file = workbench.read("appointments.csv", delimiter=";", encoding="utf-8")
```

---

## Design

**No `csv` module.** csvbench implements its own parser. Python's `csv` module assumes
the file is well-formed enough to be parsed — csvbench doesn't. The parser operates
character by character to correctly handle malformed quoting, embedded newlines, and
inconsistent delimiters.

**Multi-character separators.** The delimiter detector considers both single-character
(`|`, `;`, `\t`) and multi-character candidates (`||`, `::`) when sniffing the file.

**Pydantic v2 models throughout.** `CSVFile`, `DiagnosticReport`, `Issue`, and all
detector results are Pydantic models. This keeps the data layer typed, validated, and
serializable without extra glue code.

**CLI with two output modes.** `rich` for humans, `json` for pipelines. Both use the
same underlying models — the formatter is swapped, not the data.

---

## Contributing

Issues and pull requests are welcome.

If you find a CSV file that csvbench misparses or misdiagnoses, opening an issue with
the file (or a minimal reproduction) is already a meaningful contribution.

---

## License

MIT
