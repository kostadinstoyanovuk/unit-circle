# E4 amendment 1: reading the vintage labels and joining the four sheets of the real-time workbook

This amends `prereg/E4.md` (registered as OSF dpxqf), section 4, "Structure mapping at X.2, from headers and availability only", steps 1 and 3. It is made before any numeric cell of the workbook has been read.

## What happened

The edition selected under the release rule is "Quarter 2 (Apr to June) 2026, quarterly national accounts", released at 07:00 UK time on 30 September 2026. Its workbook was downloaded once, on 1 October 2026 (619,451 bytes; SHA-256 b6fc4ed277d9c7fe26716ba358ea5c4830f50e9f44869ebc94fdbd80159562ce; `audit/E4_ACQUISITION.json`). The structure mapping was run on it on 1 October 2026 (attempt 1). It printed the sheet names, titles, notes and header labels, and stopped at step 3 because a vintage label does not parse (`audit/e4_source/structure-attempt-1.txt` and `.json`). No numeric cell has been read or printed.

The header text shows the following.

1. **Four sheets.** The vintage-by-quarter table is held in four sheets, "1961 - 1982", "1983 - 2003", "2004 - 2017" and "2018 - ". In each, the vintage labels are in row 4 from column B and the reference-quarter labels are in column A from row 5. The sheets hold 255, 252, 174 and 67 vintage labels (748 in all).
2. **Reference quarters.** In every sheet the reference quarters run from Q1 1955 without a gap, to a last quarter that differs by sheet: Q2 1982 (110 rows), Q3 2003 (195 rows), Q1 2018 (253 rows) and Q2 2026 (286 rows). The reference-quarter labels of the four parts are therefore not identical, which section 4 step 1 requires for a join. Each shorter sheet's labels are the first labels of the longest sheet's.
3. **Vintage labels.** Every label states a month and a year, in the form "Oct-61": an English month abbreviation, a hyphen and a year of two digits. Many carry more: a price-base note in square brackets ("Sep-61 [1954 prices]", 32 labels); a code of the estimate, "M1" or "M2" (116 labels), "QNA" (92) or "1st" (33), on the next line or, in some labels of the last sheet, after a space. Four labels of the last sheet have irregular spelling or spacing: "June-26 QNA" (the month in full), "May- 2026 1st" (a year of four digits), "Aug- 26 1st " and "Nov-24 " followed by a line break and "1st". The cover sheet explains "M1", "M2" and "QNA" and the price-base notes (cells A4, A5, A6 and A13); it does not explain "1st". No label has a two-digit year from 27 to 60.
4. **Four labels out of order.** In the sheet "1961 - 1982", read as written, "Sep-62 [1958 prices]" (column H) lies between "Feb-62" (G) and "Apr-62" (I), and "Mar-62 [1963 prices]" (column CN) lies between "Feb-69" (CM) and "Apr-69" (CO): in both the release months would not increase. "Feb-772" (column GQ), between "Jan-78" (GP) and "Mar-78" (GR), has a year of three digits. In the sheet "1983 - 2003", "Aug-98 [1995 prices]" (column GI) lies between "Aug-98" (GH) and "Oct-98" (GJ); read as written it has the release month of the label before it, which step 4 allows (vintages with the same release month are ordered by their position), so the mapping would not stop there.

## The amendment

**A. Reading a vintage label (step 3).** For the vintage labels of this workbook, each run of spaces and line breaks in the text is replaced by one space and the ends are trimmed. The label must then have this form: an English month name, in full or as its first three letters; a hyphen, with spaces allowed on either side; a year of two digits or of four digits; then, optionally, a price-base note (a left square bracket, four digits, the word "prices" and a right square bracket); then, optionally, one code, "M1", "M2", "1st" or "QNA". A label of any other form does not parse, and the mapping stops at step 3 as registered.

The release month is the month named, in the year given. A year of two digits yy is read as 19yy if yy is 61 or more and as 20yy otherwise (the database's first vintage is from 1961). The price-base note and the code describe the vintage and do not change its release month. In every record a vintage is identified by its label text with each run of spaces and line breaks replaced by one space. Rule A also decides which cells of a header row are vintage labels when the vintage-by-quarter table is located in a sheet: a header cell is a vintage label if it is a date or if rule A reads it.

**B. Three labels read by place (step 3).** These header cells are read as stated here and not by rule A:

| Sheet | Column | Label as written | Release month read |
|---|---|---|---|
| "1961 - 1982" | H | Sep-62 [1958 prices] | March 1962 |
| "1961 - 1982" | CN | Mar-62 [1963 prices] | March 1969 |
| "1961 - 1982" | GQ | Feb-772 | February 1978 |

A reading by place is made only if the cell holds exactly the text listed and the labels in the columns immediately before and after it read, by rule A, as two months apart, so that the month read is the month between them (that is so for all three: February and April 1962, February and April 1969, January and March 1978). If either condition fails, the mapping stops at step 3. The label "Aug-98 [1995 prices]" (sheet "1983 - 2003", column GI) is not read by place: rule A reads it as written.

**C. Joining the four sheets (step 1).** The four sheets are the parts of one table. They are joined, in the order of their vintage ranges, when their vintage ranges do not overlap, as registered, and when the reference-quarter labels of each part are, in the same order, the first labels of the reference-quarter labels of the longest part. This condition replaces the registered condition that the labels be identical. The joined table has the reference quarters of the longest part. For a vintage of a shorter part, a reference quarter that has no row in that part is treated as an empty cell, which is no level (step 2: "a reference quarter with no row is no level"), and is counted as an empty cell in the availability table. If the labels do not satisfy the condition, or the vintage ranges overlap, the mapping stops at step 1 as registered.

By rules A and B the four parts hold vintages from September 1961 to November 1982, from December 1982 to November 2003, from December 2003 to May 2018 and from June 2018 to September 2026; the ranges do not overlap.

## Reason

Section 4 step 1 stops the mapping when parts cannot be joined under the condition of identical reference-quarter labels, and step 3 stops it when a label does not parse. Both conditions arise here, for reasons that lie in the form of the workbook and not in any value: the stop at step 3 has happened, and the stop at step 1 would follow as soon as the labels are read. The real-time database is published in four sheets by period, and a sheet lists the reference quarters up to the last quarter that its latest vintage covers, so the sheets have different numbers of rows. The vintage labels are month and year labels with codes and price-base notes that the cover sheet explains (except "1st"). Rule A takes the month and the year from the label and leaves the notes aside. Rule C joins the parts on their first labels and treats a quarter that a sheet does not list for a vintage as no level, as step 2 already does for a reference quarter with no row. Rule B reads the three header cells that the labels on either side show to be mistyped, by place, and stops the mapping if the neighbours do not agree. Only the header texts, the cover sheet and the registered text were used, and no value was read.

## What does not change

Steps 2, 4 and 5 and every other rule of section 4 apply as registered: a cell of kind other still stops the mapping (step 2); vintages are ordered by release month, vintages with the same release month by their position, and release months that do not increase in one direction stop the mapping (step 4). The workbook already acquired is the one used (section 13). Sections 5 to 11 and the annexes are unchanged. If the mapping stops again, the stop is documented and settled by a further amendment before any value is read.
