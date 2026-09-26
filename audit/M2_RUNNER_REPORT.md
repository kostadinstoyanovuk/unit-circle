# M2 validation execution preparation

26 September 2026. **The resumable runner and development recovery checkpoint are complete. M2, G1 and G2 remain open.** No official validation cell or UK observation was run or acquired.

## Implemented

- Fixed registered/development designs with separate random-seed namespaces and explicit registration checks.
- Bounded batches with atomic per-replicate persistence, a completion journal, full integrity verification and verified new backup snapshots.
- Preservation of exact inputs, generator states, complete comparisons and scientific failures. Resumption never changes a failed outcome into a replacement draw.
- Cell summaries with nominal denominators, missing/failed counts, uncertainty and the frozen acceptance rules. Development output cannot satisfy registered acceptance.

The original statistical modules, protocol and submitted package are unchanged. Added execution/storage modules call those existing methods. The fixed-date power path explicitly uses the five prescribed external positions.

## Verification evidence

The full research suite passes **236 tests**, including **32 new runner/storage tests**. Recovery coverage includes ordinary interruption, forced process termination with an uncommitted transaction, simulated write failure, concurrent writers, duplicate records, checksum corruption, missing committed records, incompatible manifests and verified-backup restoration. Direct comparisons check the runner's development calculations and generator states against the established methods.

`validation_runner_verification.json` records a separate 18-record development fixture. The run stopped after eight records, resumed to 18, and matched uninterrupted execution exactly for every retained scientific payload. A further resume added zero records. Both the eight-record and 18-record backups passed verification. The evidence includes code/protocol hashes and the scientific-record checksum; operational timestamps and batch durations are not part of the scientific equality claim.

The fixture uses master seed 20260926 and eight surrogate attempts per synthetic comparison. It is an engineering check, not a size or power estimate. All official acceptance and data gates remain pending.

## Runtime scope

The saved timing measurements cover four records per white-noise length and two records in each size/power cell on Python 3.12.14. Each size/power development record took approximately 0.24 seconds with eight surrogate attempts, including its initial fit and generation. These small measurements establish a preliminary workload scale, not an exact duration for the registered experiment. Disk synchronization, full integrity scans, backups, differing series outcomes and machine load also affect wall time. Larger official runs require bounded batches and retained checkpoints after G1; no computational optimization or design change is inferred from these timings.

## Remaining before empirical work

The OSF record remains unverified publicly. Complete contributor approval, public immutable-status and timestamp verification, archived attachment checksums and the supporting tag before official execution. Then run and review all frozen acceptance experiments. Retain any failure without retuning. Only passing G1 and G2 permits acquisition of the verified UK source. The runner's existence is not evidence that those requirements have passed.
