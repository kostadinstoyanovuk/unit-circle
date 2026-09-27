# Registered H1 execution after G2

This procedure implements plan steps S0.5 and H1.2-H1.4 under the registered protocol (`prereg/H1.md`, sections 3-12). It is closed until G1 verifies and `audit/G2_REVIEW.json` records G2 as passed. Every step fails closed; no step prints UK observation values before the registered run.

## 1. Identify the release (metadata only)

Apply the registered rule: the latest completed ONS quarterly national accounts publication released strictly before the verified public-registration timestamp, 2026-09-27T04:49:01Z (D-017). Record its title, release date and time, release-calendar URL and the release-specific ABMI file URL, all taken from official metadata. Save the ONS release-calendar evidence for QNA publications around the registration time as a JSON list of `{title, release_datetime}`. Do not open a page or file that displays ABMI values while doing this. If the release-specific file or its identity cannot be established, stop and document an amendment (section 3); there is no fallback to an unverified latest file.

## 2. Acquire once

```text
python tools/acquire_abmi.py --release release.json --calendar calendar.json --download
python tools/acquire_abmi.py --release release.json --calendar calendar.json --downloaded-file ABMI.csv --retrieved-utc 2026-...Z
```

The command re-checks G1, G2 and the release rule, then reads only the file's header records. It stops unless the header states CDID `ABMI`, source dataset `QNA`, a seasonally adjusted chained-volume title and the chosen release date. It stores the bytes read-only as `data/raw/ABMI_QNA.csv` and writes `data/raw/ABMI_acquisition.json` and a `DATA_MANIFEST.csv` row with the release title, release time, URLs, retrieval time, size, SHA-256 and licence (Open Government Licence v3.0). It refuses a second acquisition.

Commit and push the raw file and its records before the run, so the data identity is public before any result exists.

## 3. Run once

```text
python tools/run_h1.py --registered
```

From a clean checkout with Python 3.12.14 and the locked dependencies, the command verifies G1, G2 and the raw-file hash, builds the 260 levels and 259 growth rates under the section 3 stop rules, and runs every registered analysis with the registered counts and streams (B = 1,000 attempts per comparison; 10,000 episode resamples). There are no count or seed options. It writes `runs/h1-registered/` (run log, complete analysis, report, tables and figures) and refuses to run if that directory exists. The outcome wording follows section 10, with the official D80 from the G2 record for the Branch B diagnostic. A later recomputation must use `--recomputation` with a new directory and is labelled as such.

## 4. Freeze

```text
python tools/freeze_h1.py
```

The command verifies the run against its own hashes and copies the report, tables, run log, complete analysis and figures into `audit/h1/` and `figures/`, with a summary in `audit/H1_RESULT.json`. After review, commit and push, then create and push the annotated `h1-frozen` tag. The result is final whatever it says (plan H1.4).

## 5. S2 and the core note

```text
python tools/build_s2.py
make note
```

`tools/build_s2.py` fits the three registered filters to the same levels (D-021). `make note` then writes every H1, S2, release and G2 value into the core note from `audit/H1_RESULT.json`, `audit/s2_verification.json`, `data/raw/ABMI_acquisition.json` and `audit/G2_REVIEW.json`; nothing is typed by hand. The note is complete when the build reports no pending values.

## Rehearsal

`python tools/run_h1.py --rehearsal-input <artificial ONS-format file> --output-directory runs/<new>` runs the same pipeline on artificial data with shortened counts and labels every output as artificial. `tests/test_h1_official.py` builds such a file and checks the identity and sample stop rules, the release rule, the gates, the one-time acquisition record and the whole pipeline.
