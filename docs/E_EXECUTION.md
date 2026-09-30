# Registered E1 and E3 execution: X.2 data, the X.3 record, the X.4 run and the X.5 freeze

This procedure implements Annex B steps X.2-X.5 of the registered addenda `prereg/E1.md` (OSF mjg9w) and `prereg/E3.md` (OSF rhzsm) after their official synthetic checks. Every step fails closed and records what it did; no step prints an E1 value before the one-shot run. The analysis is `uc_ext.e1.analyze` and `uc_ext.e3.analyze`, frozen at X.3; the tools here (`src/uc_ext_official/`, `tools/record_e_x3.py`, `tools/acquire_e1.py`, `tools/note_e3_data.py`, `tools/run_e1.py`, `tools/run_e3.py`, `tools/freeze_e.py`) wrap it and are not part of the X.3 code identity.

## 0. Gates used by every step

- **G4**: the X.3 runner's own check (`tools/run_e_checks.py`, `verify_extension_gate`): a clean checkout, the annotated tag `prereg-Ek` published identically on origin, `prereg/Ek.md` equal to the tagged file, and `audit/Ek_REGISTRATION.json` showing an approved public registration whose archived protocol has the tagged bytes.
- **X.3 passed**: `audit/Ek_X3.json`, committed, records that the registered size and power checks passed (and, for E3, the section 11 prerequisites), with seed 1927, 200 series per cell, B = 1,000 and kappa 1.0-1.6. It states D80, or null when D80 is undefined.
- **Frozen code** (X.4 only): the code identity the X.3 runner computes (every `uc_ext` and `uc_core` source, the runner, and the environment identity under the lock and Python 3.12.14) equals the one in `audit/Ek_X3.json`.

## 1. Record the official synthetic checks (after X.3)

```text
python tools/record_e_x3.py e1 --size runs/extensions/E1/x3_size.jsonl --power runs/extensions/E1/x3_power.jsonl
python tools/record_e_x3.py e3 --prerequisite runs/extensions/E3/x3_prerequisite.jsonl \
    --size runs/extensions/E3/x3_size.jsonl --power runs/extensions/E3/x3_power.jsonl
```

Give `--size` or `--power` once per file when a check was split across processes. The outputs are summarised by `tools/run_e_checks.py summarize` in registered mode, which re-verifies the gate, the lock and every saved record. They must form one registered run of one code identity (for E3, every output names the supplied prerequisite file). The record is written once, whether the checks passed or failed; a failed check leaves every later step closed. Commit and push it.

## 2. X.2

### E1: acquire once, select by header, record the territory, extract

The E1 workbook is acquired only after `audit/E1_X3.json` records passed checks, so that no E1 value can be read before the official synthetic checks (section 11).

```text
python tools/acquire_e1.py acquire --download --licence "<licence as the Bank states it>" --licence-url <terms page>
python tools/acquire_e1.py acquire --downloaded-file <file>.xlsx --retrieved-utc 2026-...Z --licence ... --licence-url ...
```

The file served at the registered URL at the first download after verified public registration (`public_first_verified_at_utc` in `audit/E1_REGISTRATION.json`) is stored read-only as `data/raw/a-millennium-of-macroeconomic-data-for-the-uk.xlsx`, with `data/raw/E1_acquisition.json` (source and landing URLs, retrieval method and time, HTTP headers when scripted, size, SHA-256, licence, gate records) and a `DATA_MANIFEST.csv` row. Only an xlsx package is accepted as the download; an error or challenge page is not the file and nothing is recorded. A second acquisition is refused. The workbook is kept out of git (D-041): `acquire` refuses unless its path is git-ignored, and only `data/raw/E1_acquisition.json` and the `DATA_MANIFEST.csv` row are committed and pushed. The row's notes begin "Not distributed in this repository", which `tools/check_data.py` reads as: check the hash wherever a copy is present, and do not report the file missing where none is. Every later step needs the file on the machine, checks it against the committed record and refuses if git tracks it. To reproduce E1, download the file from the registered URL and check its SHA-256 against the record; the URL carries no version number, so the file it serves can change.

```text
python tools/acquire_e1.py select
```

Text only. (1) The version statement: the file qualifies when the text of its document properties, sheet names, sheet titles and cover sheet names version 3.1 and no other version; mentions elsewhere are listed, not decisive. If that title-level text also names other versions (for example a version history), read the listed statements and, if one identifies this file as 3.1, name it with `--version-location "<location as listed>"`; otherwise document an amendment. (2) The header-only output: the sheet names, each sheet's title, and the text cells above the first data row of the headline-series sheet with the notes attached to it. No numeric cell is read or printed; the first data row is the first row whose leftmost non-blank cell is numeric, located by cell type. (3) The selection rule of section 4. `audit/e1_source/header-only.txt`, `header-only.json` and `selection.json` are written once; every attempt, stopped or not, is appended to `audit/e1_source/selection-attempts.jsonl`. `--first-data-row` and `--year-column` exist only for text-only layout facts and are recorded. A stop on the rule itself (no headline sheet, no real-GDP column, or more than one after the tie-break) means: stop and document an amendment, as section 4 requires. When the amendment names the headline-series sheet, its text is committed as `prereg/E1_amendment_1.md` with a record, `audit/E1_AMENDMENT_1.json` (the registration, the text's path and SHA-256, the amendment's address, the sheet it names and the time it was first verified public). `select` then requires both files to be committed and to agree, uses only the sheet the record names (which must be one of the sheets identifying themselves as the headline series), and records the amendment with the selection; the X.4 gate requires it again. A stop because the tie-break does not leave exactly one real-GDP column is settled in the same way: the text is committed as `prereg/E1_amendment_2.md` with a record, `audit/E1_AMENDMENT_2.json` (the registration, the text's path and SHA-256, the amendment's address, the sheet, the column letter and the header text of the column it names (the column's header cells joined with " | ", exactly as the "Columns labelled as real GDP" list of the header-only output prints them, including the sheet-title and section cells in that column; differences in whitespace are ignored), and the time it was first verified public). `select` requires both files to be committed and to agree, checks that the named column is one of the real-GDP columns of the headline-series sheet and that its header text is the recorded one, uses that column, and records the amendment with the selection; where the rule already gives one column, the amendment must name that column. An amendment cannot settle a stop where no column is labelled as real GDP; that would need a further reviewed change. `extract` and the X.4 gate require every amendment the selection cites to be present, committed and unchanged. Review the header-only output and the selection before continuing.

```text
python tools/acquire_e1.py territory --record territory.json
```

The territory of each stretch 1700-2016 of the selected column, from the workbook's own notes and headers. Each stretch quotes the workbook text that states it (`{"location": "<sheet>!<cell>" | "<sheet>!<cell> (note)", "quote": "..."}`), and every quote is checked against the workbook's text. A stretch whose territory the workbook does not state is recorded as `not stated in the workbook`. The territory is documentation only: the column is used as the workbook gives it.

Commit and push every record under `audit/e1_source/`, then:

```text
python tools/acquire_e1.py extract
```

The first reading of values: the 317 levels 1700-2016 under the section 4 stop rules (through `uc_ext.e1.annual_growth`). Rows are located by their year label; values outside 1700-2016 are never read. Only counts and hashes are printed. The extraction record is written and the manifest row is completed with the version statement, sheet, column letter, header, units and territory. A stop writes `audit/e1_source/extraction-stop.json`: stop and document an amendment. Commit and push.

### E3: no download

```text
python tools/note_e3_data.py
```

After G4 for E3, the H1-registered ABMI file's bytes are re-verified against `data/raw/ABMI_acquisition.json` (no value is parsed), `audit/e3_source/data-note.json` is written and the ABMI row of `DATA_MANIFEST.csv` gains a note that E3 uses the file unchanged. Commit and push.

## 3. X.4: run once

```text
python tools/run_e1.py --registered
python tools/run_e3.py --registered
```

From a clean checkout under the lock and Python 3.12.14, each command verifies, in order: the code location (`uc_core`, `uc_ext`, `uc_ext_official` are the root's own), G4, the committed X.3 record, the frozen code, the X.2 data (E1: every record committed and the levels re-extracted identically; E3: the committed data note and `uc_core.h1_official.load_registered_growth`), and the output directory. It then runs every registered analysis with the registered seed, counts and streams; there are no count or seed options. It writes `runs/ek-registered/`: `run-log.json`, `analysis.json` (for E3 also every surrogate fit in `surrogate-fits.json.gz`), `report/` (tables, figures and `manifest.json` with every report file's SHA-256) and `RUN_COMPLETE.json` with the SHA-256 of the log, the analysis files and the report manifest. It re-reads every file against those hashes before it reports success, and refuses if the directory exists. A run that stops before `RUN_COMPLETE.json` is written leaves its directory as evidence; it is not deleted and not re-run without a dated decision. A later recomputation for verification uses `--recomputation --output-directory runs/<new>` and is labelled as such.

## 4. X.5: freeze

```text
python tools/freeze_e.py e1
python tools/freeze_e.py e3
```

The command verifies the registered run against its own hashes, refuses a rehearsal or a recomputation, copies the run log, analysis files, report tables and manifest into `audit/ek/` and the figures into `figures/ek_*`, verifies every copy, and writes `audit/Ek_RESULT.json`: the primary S, the raw p labelled "raw, not family-adjusted", m, k, K, B', q and its Wilson interval, every comparison, every episode (for E1 with its classification, the exogenous table and the territory flags; for E3 the variance estimates and boundary flags), the episode interval and the outcome in the addendum's wording. DR-E1 and DR-E3 use the Holm-adjusted p at family closure (DR-2): a raw p above 0.05 already fixes the inconclusive branch (a Holm-adjusted p is never below its raw p) and the Branch B diagnostic is reported as a labelled diagnostic; a raw p at or below 0.05 leaves the decision to family closure, and no rejection is declared from it. After review, commit and push, update `STATUS.md`, then create and push the tag:

```text
git tag -a e1-frozen -m "E1 registered result frozen" && git push origin e1-frozen
git tag -a e3-frozen -m "E3 registered result frozen" && git push origin e3-frozen
```

## Rehearsal

`python tools/run_e1.py --rehearsal-workbook <artificial workbook> --output-directory runs/<new>` runs the X.2 selection and extraction and the whole pipeline on an artificial workbook with a development seed and shortened counts; `python tools/run_e3.py --rehearsal-input <artificial ONS-format file> --output-directory runs/<new>` does the same for E3. Every output is labelled artificial and no record is touched. The tests `tests/test_e_official_*.py` build such files and exercise every stage and refusal.
