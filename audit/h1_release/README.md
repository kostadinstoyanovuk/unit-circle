# H1 release identification (metadata only)

Recorded on 28 September 2026, 22:13-22:16 UTC, after G2 passed (D-032) and before any ABMI value was acquired or inspected. This applies the registered release rule of prereg/H1.md section 3 as fixed by D-017: the latest completed ONS quarterly national accounts publication released strictly before the verified public-registration timestamp, 2026-09-27T04:49:01Z.

## Method

Official ONS release-calendar pages, one release-calendar record and one ONS search listing were loaded in a browser; titles, release dates, statuses and links were extracted programmatically from the rendered pages. No bulletin, dataset, time-series page or file that displays ABMI values was opened.

| Page | Retrieved (UTC) | Used for |
|---|---|---|
| https://www.ons.gov.uk/releasecalendar?release-type=type-published&keywords=quarterly%20national%20accounts&after-day=1&after-month=1&after-year=2025&before-day=27&before-month=9&before-year=2026&limit=100&sort=date-newest | 22:14:08 | Published quarterly national accounts publications, 1 January 2025 to 27 September 2026 |
| https://www.ons.gov.uk/releasecalendar?release-type=type-published&after-day=30&after-month=6&after-year=2026&before-day=27&before-month=9&before-year=2026&limit=100 (pages 1-3) | 22:15-22:16 | Every published release, 30 June to 27 September 2026 (201 results), without a keyword filter |
| https://www.ons.gov.uk/releasecalendar?release-type=type-upcoming&keywords=quarterly%20national%20accounts&limit=50 | 22:15:31 | The next quarterly national accounts publications |
| https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukjanuarytomarch2026 | 22:14:40 | Release-calendar record of the selected publication |
| https://www.ons.gov.uk/search?q=ABMI&content_type=timeseries | 22:14:55 | The time-series identifiers of ABMI (link titles only) |

## Result

- Selected publication: **GDP quarterly national accounts, UK: January to March 2026**, released 30 June 2026 at 7:00am UK time (2026-06-30T06:00:00Z), release-calendar record https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukjanuarytomarch2026 ("Released: 30 June 2026 7:00am").
- No quarterly national accounts publication was released after it and before the registration timestamp: the keyword listing shows none between 30 June and 27 September 2026, and neither does the unfiltered listing of all 201 releases in that interval (the only match is the publication's own time-series entry at the same time). The next is "GDP quarterly national accounts, UK: April to June 2026", confirmed for 30 September 2026 at 7:00am (06:00Z). The release published on 13 August 2026 is "GDP first quarterly estimate, UK: April to June 2026", which is not a quarterly national accounts publication.
- Series and dataset: ABMI in the QNA dataset, `/economy/grossdomesticproductgdp/timeseries/abmi/qna` (ONS search lists ABMI under the PGDP, UKEA, BB, PN2 and QNA datasets).
- File: the ONS CSV download of that series, https://www.ons.gov.uk/generator?format=csv&uri=/economy/grossdomesticproductgdp/timeseries/abmi/qna, which serves the series' current version. Until the 30 September publication that version is the one released with the selected publication. The acquisition command checks this from the file's own header before any value is read: CDID ABMI, source dataset QNA, a seasonally adjusted chained-volume title and the release date 30-06-2026. If any of these differs, it stops and nothing is stored. The time-series version listing `/timeseries/abmi/qna/previousreleases` does not exist on the ONS site (page not found, 22:15:05), so no version-specific URL is available for the current version.

`release.json` and `calendar.json` in this folder are the inputs to `tools/acquire_abmi.py`. The calendar lists every quarterly national accounts entry found from 30 September 2025 to 30 September 2026, with its UK release time, status and source listing.
