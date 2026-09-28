# First G2 review (superseded)

These files are the outputs of the first complete G2 review of the registered validation run, kept unchanged, and the diagnosis of the one problem it reported.

- `G2_REVIEW.json`, `G2_REVIEW.md`: written by `tools/review_g2.py` at commit 6260e0b, run on 28 September 2026 from 17:08 to 17:14 UTC on the complete store (SHA-256 `39cc6e018ea28f71bf2a2e28cd0376c5b09dee132d2affbc1e6e14029b8b5fba`) and the frozen summary (SHA-256 `7d2630041e2dd6d06fa27fc09915522b7506e1d92446b52f609c24fdc53dd522`). They record G2 as not passed because of one problem: "size 183 draw 256: status or onsets differ". Every other comparison agreed.
- `diagnose_size_183.py`, `diagnose_size_183.out`: a read-only diagnosis of that record, run on 28 September at about 22:00 UTC with the frozen `uc_core` modules and the independent replay. The stored attempt is labelled `no_eligible_episode` and the replayed one `no_episode`; the two paths differ by at most 2.2e-15 with no change of sign; both find one onset, at position 2, which is ineligible; p = 0.221 and K = 220 in both. No other draw of the record differs once the two labels are mapped.

The review tool was corrected in commit a4ed858 to compare outcomes rather than labels, and the complete review was re-run from that commit. Its outputs are `audit/G2_REVIEW.json` and `audit/G2_REVIEW.md`. The decision and its reasons are in DECISIONS.md, D-032.
