# H1 registration timestamp

Checked 27 September 2026. This record resolves the public-registration timestamp that H1 section 3 uses to select the QNA publication. It relies on saved public registry and release-calendar metadata; no UK observation, bulletin or dataset was opened.

## Registry evidence

| Event | UTC time | Source |
|---|---|---|
| Registration record created and frozen at submission | 2026-09-25T15:32:12.994Z | OSF API `date_registered` |
| Pending approval observed; anonymous API returned HTTP 401 | 2026-09-26T19:11:17Z | Recorded verification observation |
| Original registration response recorded as approved | 2026-09-27T04:49:01.989Z | OSF API schema response `date_modified`, `reviews_state: approved` |
| Registration copy public on the Internet Archive | 2026-09-27T04:50:09Z | Internet Archive item `osf-registrations-wcnbz-v1`, `publicdate` |
| First anonymous verification of the approved public record | 2026-09-27T20:58:15.037Z | OSF API, HTTP 200, `revision_state: approved` |

The registration was submitted for immediate public visibility. The governing public-registration timestamp is therefore the registry's recorded approval, **2026-09-27T04:49:01Z**. The Internet Archive publication 68 seconds later and the first anonymous verification bound it independently. The activity log of the source project, which records approvals, requires authentication and is not part of this public evidence.

The saved OSF and Internet Archive responses are in `registration-evidence/2026-09-27/` with their retrieval times and SHA-256 values. `tools/verify_registration_timestamp.py` re-checks those bytes, the registry states and the event order, and writes `h1_timestamp_verification.json`.

## Effect on the release rule

H1 selects the latest completed ONS quarterly national accounts publication released strictly before the verified public-registration timestamp. The admissible interval runs from submission, 2026-09-25T15:32:12Z, to the first anonymous verification, 2026-09-27T20:58:15Z.

The ONS release calendar lists five publications for 25-27 September 2026, all at 09:30 UK time on 25 September and none a QNA publication. The next QNA publication, *GDP quarterly national accounts, UK: April to June 2026*, is confirmed for 30 September 2026 at 07:00 UK time. No QNA publication was released inside the interval, so every admissible timestamp selects the same publication. The choice among the registry timestamps therefore cannot affect the data vintage (D-017).

The identity of that publication, its release-specific ABMI file and file availability are not established here. They are resolved after G2, before any values are inspected, and the registered stop-and-amend rule applies if they cannot be verified.
