# E1 amendment 2: the real-GDP column of the headline-series sheet

This amends `prereg/E1.md` (registered as OSF mjg9w), section 4, "Selecting the series without seeing values (X.2)", as amended once already: amendment 1, approved on 30 September 2026 at 06:48 UTC, names the sheet "A1. Headline series". This amendment is made before any numeric cell of the workbook has been read.

## What happened

On 30 September 2026 at 06:56 UTC the header-only script was run on sheet A1. It printed the text cells of the sheet above the first data row, and the columns whose header labels them as real GDP. There are seven (columns B, D, F, H, J, L and N). Five of them (B, D, F, L and N) name the UK or a geographically consistent estimate in their header (the words "UK", "United Kingdom" or "geographically consistent"); on a stricter reading at least B and D still do, so on either reading the tie-break in section 4 does not identify exactly one column. The selection stopped. The stopped attempt is recorded in `audit/e1_source/selection-attempts.jsonl` (repository commit 91b6a07). No numeric cell has been read.

The five columns, by the text in their header (description in row 4, units in row 6):

- B: "Real UK GDP at market prices, geographically-consistent estimate based on post-1922 borders"; "£mn, Chained Volume measure, 2013 prices".
- D: "Real UK GDP at factor cost, geographically-consistent estimate based on post-1922 borders"; "£mn, Chained Volume measure, 2013 prices".
- F: "Index of real UK GDP at market prices cost - based on changing political boundaries,"; "GB before 1801, GB+Ireland 1801-1920, GB + Northern Ireland after 1920.  Indexed to 100 in 1920".
- L: "Composite estimate of English and (geographically-consistent) UK real GDP at factor cost"; "2013=100".
- N: "HP-filter of log of real composite estimate of English and UK real GDP at factor cost"; "approx. % difference from trend".

The other two real-GDP columns, H and J, are labelled as England only.

## The amendment

The real-GDP column is column B of the sheet "A1. Headline series", described in its header (row 4) as "Real UK GDP at market prices, geographically-consistent estimate based on post-1922 borders".

## Reason

Section 4 requires a stop and an amendment when its tie-break does not give exactly one column. Column B is described in its header as the UK, geographically consistent estimate of real GDP at market prices, in £mn, chained volume measure at 2013 prices: a level series valued at market prices. The ONS describes the real-time database of its series ABMI, the series used in H1, as "Quarterly levels for UK gross domestic product (GDP), in chained volume measures at market prices" (`prereg/E_SOURCE_METADATA.md`, section 3, under E4). Column D is the same estimate at factor cost. Column F is an index on changing political boundaries, column L is an index of a composite that includes English data, and column N is described as an approximate percentage difference from trend, not a level. Only the header texts of the workbook and the registered source metadata were used, and no value was read.

## What does not change

Everything else in section 4 applies to column B as registered: the territory record, the sample (317 annual levels, 1700-2016) and its stop rules. The worksheet label in the header of column B (row 5) reads "A8. Real GDP (A) 1700-2015"; this label does not change the registered sample, which is 1700-2016 inclusive. If column B lacks a numeric level for any year from 1700 to 2016, or ends before 2016, extraction stops, no value is printed, and a further amendment is documented, as section 4 requires; the sample is not shortened, and the further amendment states which years were missing. Amendment 1 and the rest of the addendum are unchanged. Any further stop is documented in the same way, before any value is printed or used in an analysis.
