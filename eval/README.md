# Evaluation set

The labelled workbooks behind Daftar's published accuracy (contract C-6).

| Path | What it holds |
|---|---|
| `LABELLING.md` | How to label, in English, French and Arabic |
| `replicas/build.py` | Builds the invented SME replicas in `workbooks/` |
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
- **Test labels start blank.** Correcting the analyser's guesses pulls a person towards them, and the test split is what gets published. The screen and `--prelabel` both enforce this.
- **Workbooks that shaped the rules stay in dev.** Everything in `private/pool/` was used to tighten the analyser, so none of it can be a fair test. The test split needs workbooks the rules were never tuned on.
- **A label holds workbook data.** It stores formula results, so a private workbook's label must not be committed. Labels of `sb_*` workbooks are git-ignored for that reason.
- **Replicas stay out of the published number.** Their author also wrote the analyser, so they may suit it without meaning to. They stay in dev, or are reported under their own name and never in the headline.
- **Check before reuse.** Scan for personal data before adding a workbook. Enron files contain SSNs and birth dates.

## Commands

```sh
# Label in the browser, at http://127.0.0.1:8790. It serves this machine only.
uv run daftar label --labels eval/labels --who "Your name"

# Run the analyser and score it against the labels. Reports go to the -o folder.
uv run daftar eval --labels eval/labels --split dev -o reports/dev

# Or score analyses that already exist.
uv run daftar eval --labels eval/labels --split dev --analyses analyses/ -o reports/dev

# Write draft labels for a person to correct. Existing labels are never overwritten.
uv run daftar eval --labels eval/labels --split dev --prelabel --analyses analyses/ -o drafts/

# Freeze the test split.
uv run daftar eval --labels eval/labels --split test --freeze -o reports/freeze
```

`analyses/` holds `<id>.json` (C-2) and, for the formula metric, `<id>.parity.json`: `{"results": [{"sheet", "ref", "value"}]}`, with the value each formula evaluated to.
