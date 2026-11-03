# Evaluation set

The labelled workbooks behind Daftar's published accuracy (contract C-6).

| Path | What it holds |
|---|---|
| `manifest.csv` | One row per workbook: id, source, licence, language, stratum, split, consent, sha256 |
| `labels/<id>.json` | The human labels, checked against `daftar_worker/evaluation/label.schema.json` |
| `workbooks/` | Workbooks that may be published |
| `private/` | Git-ignored. Workbooks that may not be published, including anything from a client |
| `test-frozen.json` | The frozen test split. Once it exists, rows can be added but not changed or removed |

## Rules

- **Never tune on the test split.** Its report holds no per-workbook detail, so its mistakes can't feed back into the rules.
- **A draft label doesn't count.** Pre-labelled files have `"status": "draft"` and scoring refuses them until a person has corrected them and set `"status": "reviewed"`.
- **Stress workbooks stay out of the headline.** They are oversampled for rare features, so they're reported only under their own stratum.
- **A workbook with no analysis scores as wrong**, and the report lists it. It's never skipped.
- **Check before reuse.** Scan for personal data before adding a workbook. Enron files contain SSNs and birth dates.

## Commands

```sh
# Score analyses against the labels. Reports go to the -o folder.
uv run daftar eval --labels eval/labels --split dev --analyses analyses/ -o reports/dev

# Write draft labels for a person to correct. Existing labels are never overwritten.
uv run daftar eval --labels eval/labels --split dev --prelabel --analyses analyses/ -o drafts/

# Freeze the test split.
uv run daftar eval --labels eval/labels --split test --freeze -o reports/freeze
```

`analyses/` holds `<id>.json` (C-2) and, for the formula metric, `<id>.parity.json`: `{"results": [{"sheet", "ref", "value"}]}`, with the value each formula evaluated to.
