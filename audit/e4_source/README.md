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
