# convert-mindmup-freemind

Convert mind maps saved in [MindMup](https://www.mindmup.com/) format (`.mup`) to [FreeMind](https://freemind.sourceforge.net/) format (`.mm`).

## Features

- Converts **MindMup JSON** (`.mup`, current format) and **legacy MindMup XML** exports — format is auto-detected from file content.
- Accepts a **single file** or an **entire directory** (scanned recursively).
- Preserves the left/right branch layout: negative-keyed children become `POSITION="left"`, positive-keyed children become `POSITION="right"`.
- **No external dependencies** — uses Python's standard library only (`json`, `xml.etree.ElementTree`, `argparse`).

## Requirements

- Python 3.9 or later (3.12 recommended)

## Usage

```bash
# Convert a single file
python convert.py path/to/map.mup output/

# Convert all .mup files in a directory (recursive)
python convert.py path/to/maps_dir/ output/
```

Output files are written as `<original-name>.mm` in the specified output directory (created automatically if it does not exist).

Files that cannot be parsed are skipped with a warning; all other files in the batch are still converted.

## Format notes

| Aspect | MindMup JSON | FreeMind XML |
|---|---|---|
| Extension | `.mup` | `.mm` |
| Encoding | JSON | UTF-8 XML |
| Branch key | Numeric string (`"1"`, `"-1"`) | `POSITION` attribute |
| Nesting | `ideas` object | Nested `<node>` elements |

## Running tests

```bash
python -m unittest discover tests
```

## Project structure

```
convert.py          # CLI entry point + conversion logic
tests/
  test_convert.py   # unittest-based test suite
  fixtures/
    sample.mup          # MindMup JSON example
    sample_legacy.mup   # Legacy MindMup XML example
    sample.mm           # Expected FreeMind output for sample.mup
```
