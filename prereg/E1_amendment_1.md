# E1 amendment 1: the headline-series sheet

This amends `prereg/E1.md` (registered as OSF mjg9w), section 4, "Selecting the series without seeing values (X.2)". It is made before any numeric cell of the workbook has been read.

## What happened

On 29 September 2026 at 19:36 UTC the workbook at the registered file URL was downloaded once, after the registration was first verified as public (2026-09-28T15:57:37+00:00). It has 27,533,690 bytes and SHA-256 4c23dd392a498691eac92659aec283fb43f28118bd80511dc87fc595974195eb. Its own contents identify it as version 3.1: a sheet named "Corrections to V3.1" and a front-page entry "What's new in version 3.1 ?".

At 19:37 UTC the header-only script listed the workbook's 109 sheets. Three have a name or title that identifies them as a headline-series sheet:

- "A1. Headline series", titled "A1. Headline Annual Series 1086-2016";
- "Q1. Qrtly headline series";
- "M1. Mthly headline series".

Section 4 takes the series from "the headline-series sheet" and requires a stop and an amendment when the rule does not give exactly one. The script stopped. The stopped attempt is recorded in `audit/e1_source/selection-attempts.jsonl` (repository commit 41d655a). No numeric cell has been read, and no header text of sheet A1 beyond its title has been printed.

## The amendment

The headline-series sheet is the annual headline-series sheet, "A1. Headline series".

## Reason

Section 4 quotes the plan's description of the series, "the headline annual real GDP series from 1700", and its sample is 317 annual levels, 1700-2016. Of the three sheets, only A1 is annual; the other two are named as the quarterly and the monthly headline series.

## What does not change

Everything else in section 4 applies to sheet A1 as registered: the rule for the real-GDP column and its tie-break (the column described as the UK or geographically consistent estimate), the territory record, the sample and its stop rules. The rest of the addendum is unchanged. Any further stop is documented in the same way, before values are read.
