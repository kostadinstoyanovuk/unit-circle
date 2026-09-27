# S1.1: transcription of Yule (1927)

28 September 2026. Source: G. U. Yule (1927), *Phil. Trans. R. Soc. A* 226, 267-298, doi:10.1098/rsta.1927.0007; the publisher's scanned PDF of all 32 pages (SHA-256 `766518d7…2993c`), which is not redistributed here. Transcribed values: [yule1927.csv](../data/transcribed/yule1927.csv) (sample, equations and periods, each with its page and printed wording) and [yule1927_tableA.csv](../data/transcribed/yule1927_tableA.csv) (Wolfer's numbers, 1749-1924, Table A, pp. 297-298). Evidence: [yule1927_verification.json](yule1927_verification.json), rebuilt by `tools/build_yule1927.py`.

## What Yule reports

For Wolfer's sunspot numbers, 1749-1924 (p. 275), the regression equation (31), p. 281, is

u_x = 1.34254 u_{x-1} - 0.65504 u_{x-2} + 13.854,

with roots 0.67127 ± 0.45215i, θ = 33.963°, period 10.600 years, damping λ = -0.21154 and disturbance s.d. 15.41. His first, harmonic equation (15), p. 275, gives 10.08 years; the graduated numbers give 11.164 years by equation (32), p. 282.

## The transcription was checked twice

1. **Two readings.** The scan's text layer and a reading of the pages rendered at 300 dpi agree on all 176 Wolfer numbers. The text layer mislabels the year 1840 as "1810"; the value is unaffected. Every printed result in `yule1927.csv` was compared with the text layer; the constant 12.854 of equation (32) was confirmed from the page image because the text layer truncates that line.
2. **Yule's own arithmetic.** Yule printed a disturbance for every year from 1751, computed from equation (31) with coefficients cut to three decimals (p. 282). Recomputed from the transcription, 171 of 174 agree with the printed values to rounding (0.06). Every Wolfer number enters three of these equations, so each value is confirmed independently of the reading.

Three printed disturbances disagree with Yule's own numbers: 1789 (printed +15.2, recomputed +14.91), 1830 (+8.4 against +8.10) and 1832 (-3.8 against -4.04). The Wolfer numbers entering them are unambiguous in the scan and are confirmed by their other equations, so these are slips in the printed table, not transcription errors.

## Yule's numbers are reproduced

- Rounding the deviations from the mean to the nearest unit, as Yule states (p. 275), reproduces his Table IV serial correlations exactly: r1 = 0.811180 and r2 = 0.433998 (p. 287). Without the rounding they would be 0.811811 and 0.434629.
- Those correlations give equation (31)'s coefficients to within 1e-5. The printed coefficients give the printed period, 10.600 years.
- The disturbance s.d. is reproduced (15.41), and the series s.d. is 34.67 against the printed 34.66.

## Yule's sample and the later series

Yule's Table A differs from SILSO's frozen Version 1 file in 49 of the 176 years, by up to 1.7. The largest differences are 1828 (62.5 against 64.2) and 1840 (63.2 against 64.6). It differs from the statsmodels yearly series in 22 years.

On Yule's own numbers the programme's least squares gives (1.3363, -0.6504), modulus 0.806 and a period of 10.57 years, the same as AT-1 to four decimals. The programme's Yule-Walker convention, with one common denominator, gives 10.54 years. Yule's 10.600 years therefore reflects his correlation arithmetic rather than his data. The version change from V1 to V2 moves the least-squares period by +0.07 years ([S1 table](S1_TABLE.md)).
