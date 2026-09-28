# Source metadata record: E1–E4 addenda

Investigator: Kostadin Stoyanov. Prepared 28 September 2026. All times UTC. This record covers every web page, search and fetch made to prepare the E1–E4 addenda. The rule applied was P2 and gate G4: documentation and metadata pages only. No extension data file was downloaded, opened or previewed, and no UK observation of any kind was read.

## 1. How pages were read

Pages were fetched with `curl` through a small script, not retained. The script:

- refuses any URL that looks like a data file (`.xls`, `.xlsx`, `.csv`, `.zip`, `.json`, `.xml`, `.txt`, `.dat`, ONS `/data` endpoints and ONS `/generator?` download links);
- strips scripts and markup;
- prints only the text lines matching a stated keyword filter;
- records UTC time, HTTP status, byte count and the SHA-256 of the HTML response.

Follow-up extractions from the same pages printed release-date fields, edition labels and link targets. They did not follow any link. Three site-restricted web searches (`ons.gov.uk` or `bankofengland.co.uk`) returned titles, URLs and a search summary. Two summarising page fetches asked for metadata only and excluded values.

The SHA-256 values identify the HTML each server returned at that moment. The pages are dynamic, so a later fetch may differ. The HTML was not committed.

## 2. Pages visited

| # | UTC | URL | HTTP | Bytes; SHA-256 (first 16 hex) | Printed | Used for |
|---|---|---|---|---|---|---|
| 1 | 04:07:23 | https://www.bankofengland.co.uk/statistics/research-datasets | 200 | 91,320; `4c55b587bfb61afb` | Lines matching millennium, version, 1700, spreadsheet, headline | E1 identity |
| 2 | 04:07:33 | same page (re-fetch) | 200 | not recorded | The full "A millennium of macroeconomic data" paragraph and its three link targets. The links were listed, not followed. | E1 identity, version, coverage end |
| 3 | 04:07:42 | https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms/previous | 200 | 248,316; `929cda96170189e5` | Series title, series ID, dataset, archive description | E2 series identity |
| 4 | 04:07:54 | same page (re-fetch) | 200 | not recorded | Release-date and next-release fields; superseded-version labels (dates only) and download-link pattern. No link followed. | E2 release rule |
| 5 | 04:08:02 | https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/methodologies/labourforcesurveyqmi | 404 | 27,061; `c9f76b52069593ed` | nothing | — |
| 6 | 04:08:03 | https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/labourmarketstatistics | 200 | 43,960; `52997fb2c6a0e782` | Dataset title, ID and description lines | E2 dataset identity (LMS) |
| 7 | 04:08:10 | https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/methodologies/labourforcesurveylfsqmi | 200 | 76,192; `6f5bd337e8fd893b` | Lines matching 1971, 1984, 1992, calendar quarter, rolling, release | E2 coverage caveat |
| 8 | 04:08:11 | https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/methodologies/aguidetolabourmarketstatistics | 200 | 89,315; `15681f944a1a905c` | Lines matching 1971, 1992, quarterly, three-month | E2 coverage from 1971 |
| 9 | 04:08:37 | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi | 200 | 176,388; `9a2c25c03e36c3cf` | Title, description, edition labels and file sizes | E4 source identity |
| 10 | 04:08:38 | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/revisionstrianglesforukgdpabmi | 200 | 164,773; `f385bd6ea5352a38` | Title, description, edition labels | E4 alternative source |
| 11 | 04:08:50 | pages 9 and 10 (re-fetch) | 200 | not recorded | Release-date fields, number of edition rows, oldest listed edition labels | E4 release rule and coverage |
| 12 | ≈04:09 | Web search "ONS GDP revisions triangles real-time database ABMI dataset" (ons.gov.uk) | — | — | Titles and URLs | Located pages 9–10 |
| 13 | ≈04:09 | Web search "Bank of England GDP real-time database vintages" (bankofengland.co.uk) | — | — | Titles, URLs, search summary | Located page 15 |
| 14 | 04:09:09 | https://www.bankofengland.co.uk/statistics/gdp-real-time-database | 404 | 55,911; `d140e048626a84cf` | Site menu text only | E4 Bank candidate: not available |
| 15 | 04:09:09 | https://www.bankofengland.co.uk/statistics/data-collection/real-time-database (guessed URL) | 404 | 55,912; `55e1e92326492363` | Site menu text only | — |
| 16 | ≈04:09–04:10 | https://www.bankofengland.co.uk/statistics (twice) and page 14 again, searched with `grep` for the menu entry | 200 / 404 | not recorded | Only the anchor `href="/statistics/gdp-real-time-database"` labelled "Gross Domestic Product Real-Time Database" | Confirmed the site menu still links to the 404 page |
| 17 | ≈04:10 | Summarising fetch https://www.bankofengland.co.uk/statistics/gdp-real-time-database | 404 | — | "HTTP 404 Not Found" | Confirms page 14 |
| 18 | ≈04:10 | Web search "ONS real-time database GDP ABMI vintages coverage since 1961 explanatory notes revisions analysis methodology" (ons.gov.uk) | — | — | Titles, URLs, search summary | No coverage documentation found |
| 19 | ≈04:10 | Summarising fetch https://www.bankofengland.co.uk/quarterly-bulletin/2002/q1/building-a-real-time-database-for-gdpe (landing page only) | 200 | — | Tool summary under a metadata-only prompt | E4 Bank candidate history |

Times marked ≈ come from the order of retrieval, because those searches returned no timestamp.

## 3. What the metadata establish

These facts are stated as the pages gave them on 28 September 2026. None was checked against a data file.

**E1. Bank of England, A millennium of macroeconomic data** (page 1–2):

- The page describes "a broad set of macroeconomic and financial data for the UK stretching back in some cases to the C13th".
- It was "originally called the 'Three centuries of macroeconomic data' spreadsheet".
- It states: "Version 3.1 of the dataset has now been updated to 2016."
- The single download link is `/-/media/boe/files/statistics/research-datasets/a-millennium-of-macroeconomic-data-for-the-uk.xlsx`, labelled 28MB. This URL carries no version number.
- The page states that it was last updated on 20 May 2026. That date belongs to the page, not to the dataset.
- Not established: the sheet, column and territory of the headline annual real GDP series, and whether it starts in 1700. The plan (p. 12) states these, but they can be read only from the workbook, at step X.2.

**E2. ONS MGSX** (pages 3–8):

- Series ID `MGSX` is titled "Unemployment rate (aged 16 and over, seasonally adjusted): %". It belongs to dataset `LMS`, "Labour market statistics time series".
- Current release date: 15 September 2026. Next release: 20 October 2026.
- The previous-versions archive lists superseded files back to 16 December 2015 (latest archived version id `v127`). Labels are "Date superseded", not release dates, as for ABMI (research repo D-016).
- The labour market guide states: "Estimates of total unemployment levels and rates for the UK are available from 1971."
- The LFS methodology page (last revised 17 November 2025) states:
  - "The LFS began in 1973, and it was carried out every two years until 1983. Between 1984 and 1991, data were collected annually."
  - Quarterly sampling has run "since spring 1992, with a change from seasonal to calendar quarters in 2006".
  - Rolling quarters were produced from January 2020 to March 2022.
- **Consequence.** Quarterly MGSX values before 1992 cannot all be direct quarterly LFS survey estimates. How ONS constructed them was not established from metadata (unverified). E2 records this as a disclosed limitation and an owner decision (research repository D-023, E2-1).

**E4. Real-time GDP** (pages 9–19):

- ONS "GDP in chained volume measures – real-time database (ABMI)" gives "Quarterly levels for UK gross domestic product (GDP), in chained volume measures at market prices". The latest edition is "Quarter 2 (Apr to June) 2026, first estimate", released 13 August 2026. The next release is 30 September 2026.
- The page lists 84 editions, the oldest labelled "Quarter 4 (Oct to Dec) 2015, Month 3". Each edition is one xlsx workbook of about 0.6 MB.
- ONS "GDP in chained volume measures – revision triangles (ABMI)" gives growth rates and revisions, not levels. Its latest release was 30 June 2026 and its next is 30 September 2026.
- **Not established from metadata:** the earliest vintage, and the earliest reference quarter, contained in a real-time database edition. No ONS page found states them. This is the main unresolved coverage question for E4 (research repository D-023, E4-1).
- The Bank of England site menu still links "Gross Domestic Product Real-Time Database" to `/statistics/gdp-real-time-database`. That URL returned HTTP 404 at 04:09:09 and again through a summarising fetch.
- The Bank's 2002 Q1 Quarterly Bulletin landing page (Castle and Ellis, "Building a real-time database for GDP(E)", 1 March 2002) describes an expenditure-measure GDP database of successive releases starting in 1961. This is the tool's summary; the article PDF was not opened. The Bank candidate is therefore not available at its advertised location on this date.

## 4. Deliberately not opened

- The millennium workbook (`a-millennium-of-macroeconomic-data-for-the-uk.xlsx`), because it is E1 data.
- The Bank of England Quarterly Bulletin 2010 Q4 article "The UK recession in context — what do three centuries of data tell us?", linked from page 1. It describes the E1 data and UK recession history, so reading it would expose E1 outcomes before registration.
- The ONS MGSX series landing page (`…/timeseries/mgsx/lms`), because it displays the latest value. Also every MGSX `.xls` and `.csv` generator link, and the LMS dataset files.
- Every ONS real-time database and revision-triangle workbook.
- The ONS ABMI series pages and files. ABMI is H1's data under H1's own rules, and no ABMI observation is needed to draft these addenda.
- The Bank of England 2002 Quarterly Bulletin PDF and any Bank working paper about GDP revisions. These may report revision statistics.

## 5. Incidental exposure

No numerical GDP, unemployment or revision value appeared in any printed line. The search summary of search 18 mentioned an ONS quality review of software investment within GFCF (about 1.1% a year from 1997). That concerns a GDP component's level, not E1–E4 series. It is recorded here for completeness.
