# Bounded validation runner

The runner implements H1 sections 8 and 9 using the existing estimators, synthetic generator, endogenous-onset comparison and externally fixed-date power comparison. It does not acquire observations or change the submitted design. Official execution is unavailable until the independently verified registration receipt satisfies G1.

## Development and registered modes

Both modes require explicit selection. Registered mode fixes the submitted master seed, stream coordinates, replicate counts and 1,000 surrogate attempts. There are no command-line overrides for those scientific settings. Development mode uses the separate master seed 20260926, four series at each white-noise length, two series in each size/power cell and eight surrogate attempts. Its 18 records cannot pass AT-5, AT-15 or AT-16 and cannot produce an official D80.

Registered mode checks the receipt's passed G1, anonymous HTTP 200/public verification, immutable-record verification, timezone-aware public timestamps, all five archived hashes, identical protocol bytes and an annotated `prereg-H1` tag matching the published tag. The receipt must contain actual independently checked evidence; setting a flag is not a substitute for that check. The current pending receipt deliberately fails. Required completed-receipt fields include `public_immutable_verified: true` and `archived_attachment_sha256` matching `expected_attachment_sha256`.

The runner records the exact commit, source hashes, dependency versions, Python version and numerical runtime configuration. Registered mode requires a clean checkout and Python 3.12.14. Resumption requires an identical manifest. Preserve the original checkout and environment for an interrupted official run; changing code, commit, environment, design or receipt identity is not silent continuation. Outputs belong in ignored `runs/` or outside the repository.

## Durable records and recovery

Each completed replicate is a compressed canonical JSON record in SQLite, keyed uniquely by cell and replicate, with a SHA-256 checksum. The record and its completion-journal entry commit in one transaction with full synchronization. The application never updates or replaces a completed record. An interrupted transaction rolls back; restart recomputes only that unfinished coordinate with the same stream. A committed scientific failure remains a completed failed outcome and is never automatically rerun.

Before resuming or summarising, verify the complete database, frozen manifest, record checksums, payload identities and one-to-one completion journal. Missing committed records, duplicate entries, incompatible identities or corrupted payloads stop the run. A transaction locks before checking/computing its next coordinate; a concurrent writer fails promptly. The store is intended for a local filesystem, not simultaneous network-share execution.

Inputs, generation states, analysis states, observations, null fits, surrogate statistics/statuses and explicit errors are retained. White-noise records preserve their exact generated inputs, fitted coefficients and discriminant. Size/power records preserve the complete comparison and surrogate precision. Requested, valid, failed and unfinished outcomes remain distinct; failed white-noise fits are not classified as real roots. Fixed-date power uses the five external positions even without negative-growth episodes.

Checksums protect against accidental alteration, not an adversary rewriting both data and checksums. Keep independent backups. The backup operation writes a new snapshot and verifies it; it refuses to replace an existing file. An interrupted backup can leave an unusable file, so retain the working database and use a new backup name. Do not copy an actively writing database as a substitute for the provided snapshot operation.

## Example: development checkpoint

```text
python tools/run_validation.py run --mode development --database runs/development/validation.sqlite --create --max-new 8 --backup runs/development/after-8.sqlite
python tools/run_validation.py run --mode development --database runs/development/validation.sqlite --max-new 10 --backup runs/development/after-18.sqlite
python tools/run_validation.py verify --database runs/development/validation.sqlite
python tools/run_validation.py summary --database runs/development/validation.sqlite --summary-output runs/development/summary.json
```

`--max-new` limits newly completed records, including explicit failures; it does not change the nominal cell size. Re-running a complete database performs no further replicate work. New summaries use new filenames so earlier incomplete summaries remain available. The CLI prints a bounded batch duration and summary. Preserve that output with the run record. Summarising a saved database does not rerun experiments or require that the currently installed numerical environment match its historical one.

## Verification

`tests/test_validation_runner.py` covers exact stream/wiring comparisons, preserved failures, normal restart, a forced process exit, rollback during a simulated write failure, duplicate/concurrent writers, changed designs/environments, damaged/missing records, backup restoration and incomplete denominators. Registered counts are inspected without constructing registered random generators. Constructed accounting fixtures are not calibration results.

For a fresh development-only recovery comparison:

```text
python tools/verify_validation_runner.py --output-directory runs/new-recovery-check --report runs/new-recovery-check/report.json
```

The output directory must not already exist. The check interrupts after eight white-noise records, resumes the remaining ten records, compares all scientific payloads with an uninterrupted execution, verifies two backups and confirms that another resume adds zero records. See `audit/M2_RUNNER_REPORT.md` for the recorded checkpoint and limitations.

## Acceptance review remains separate

Cell summaries retain all nominal denominators, errors, accounting bounds and Monte Carlo precision. A partial or invalid cell cannot pass its acceptance target. The official power summary uses the existing unsmoothed first-crossing rule only when the required cells are valid. No summary automatically passes G2: that gate also requires the full baseline and estimator evidence, protocol identity and a recorded review. A failed calibration is retained and addressed under the registered deviation rules before any UK data access.
