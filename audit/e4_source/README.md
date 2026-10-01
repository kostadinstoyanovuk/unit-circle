# E4 coverage documentation: ONS pages read on 29 September 2026

These files record how the coverage of the ONS real-time database for GDP (ABMI), the source adopted for extension E4 (`DECISIONS.md` D-023, E4-2), was sought before E4 was registered (D-044; `prereg/E4.md` Annex C).

- `guarded_fetch.py` (SHA-256 `822a236e00ef50ef524764c682d66a788ad6bd465c1807f240ff61eca0863cf4`) made every request. It refuses any address that is not on its fixed list of documentation pages, or that points to a data file, a bulletin, a time series, an article, an ad hoc release or a download; it does not follow redirects; it saves each response and logs the request; and it prints only the visible text of a page outside tables, with decimal numbers, percentages, currency amounts, thousands-separated numbers and numbers of five or more digits replaced by `[num]`.
- `ons-requests-2026-09-29.jsonl` is its request log, one JSON object per request, with line ends normalised to LF (SHA-256 `2778dfc212083dbbf87dd1cfe7f50001ebbdee7956d649d9b907ce61d6e69acf`).

| # | Request (UTC) | Address | HTTP | Bytes | SHA-256 of the saved response |
|---|---|---|---|---:|---|
| 1 | 2026-09-29T19:53:08Z | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi | 200 | 176,388 | `caef462265f03d648cce371e5beca175308ab678edc907e2ee1932ee582979b1` |
| 2 | 2026-09-29T19:53:35Z | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/revisionstrianglesforukgdpabmi | 200 | 164,773 | `6264e0844d5e11e3a0386a5965a0cf0cf3d81fa34ee06bce54958ec84c6ba1b0` |
| 3 | 2026-09-29T19:53:40Z | https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/revisions/revisionspoliciesforeconomicstatistics/nationalaccountsrevisionspolicyupdateddecember2017 | 200 | 54,239 | `26b128072f5ceea19646db44bbf95bf830db358a8bc8f3c7bbbfa73d29052c1a` |
| 4 | 2026-09-29T19:53:50Z | https://www.ons.gov.uk/economy/grossdomesticproductgdp/methodologies/grossdomesticproductgdpqmi | 200 | 100,220 | `12fda44cc0cda84d56b8530cdf06f4582158065d4c308f5a254f479512e92c59` |
| 5 | 2026-09-29T19:54:01Z | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi/quarter4octtodec2017month2 | 200 | 36,740 | `95844f500247484681dd2994925f8c08016fb21e132b26e70a45a6e1b4ad2c68` |
| 6 | 2026-09-29T19:54:15Z | https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukjanuarytomarch2026 | 200 | 52,169 | `9b29d621a870405f0335ad39fc227d9a6b8991dc705c50484c4a2dfcf91bffb2` |

The saved pages themselves are kept with the programme's preparation records and are not reproduced here; each can be checked against the SHA-256 above. No workbook, archive, bulletin, time-series page or other data page was opened. What the pages state, and what they do not, is set out in `prereg/E4.md` Annex C.

## X.2: pages saved on 1 October 2026

The release rule of `prereg/E4.md` section 4 needs the release date and time of the edition. After the release of 30 September 2026, two pages were saved with `tools/acquire_e4.py list --fetch`, which applies an address list of its own (`docs/E4_X2_READINGS.md`, R-X2.6) and requested nothing else. `ons-requests-2026-10-01.jsonl` is its request log, one JSON object per request, with line ends normalised to LF (SHA-256 `b962cdbd56fc7d7ccb8c39a6f66999c8616ed035a027b69d61b6f4ad742d8ce4`).

| # | Request (UTC) | Address | HTTP | Bytes | SHA-256 of the saved response |
|---|---|---|---|---:|---|
| 7 | 2026-10-01T04:53:00Z | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi | 200 | 178,091 | `0636cf8deca84482109d5ff1a960e540f70ed3d48650c153021b5d51970391dc` |
| 8 | 2026-10-01T04:53:00Z | https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukapriltojune2026 | 200 | 52,547 | `ba28e7ab85b210581114af2998480860084937ac605287f7f336b7911169050a` |

The dataset page states "Release date: 30 September 2026" and "Next release: 12 November 2026". The release-calendar record "GDP quarterly national accounts, UK: April to June 2026" is published, gives 30 September 2026 at 7:00am UK time, lists the dataset and gives the same next release. The registration was verified public at 06:27:00.9 UTC on 30 September 2026 (07:27 UK time), so the edition "Quarter 2 (Apr to June) 2026, quarterly national accounts" was released in the minute from 06:00 UTC, before it. The saved dataset page lists that edition first and dates the next release 12 November 2026, so no later edition was released before the registration (R-X2.2, R-X2.4). `edition.json` records the listing, every edition considered with its reason, the pages used and the choice. The pages are kept with the programme's preparation records, and each can be checked against the SHA-256 above. No workbook was requested at this step.
