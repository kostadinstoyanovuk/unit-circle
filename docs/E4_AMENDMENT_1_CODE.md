# E4 amendment 1 in the X.2 code: reading the vintage labels and joining the four sheets

This document maps the draft of E4 amendment 1 (reading the vintage labels and joining the four sheets of the real-time workbook; it amends `prereg/E4.md` section 4, steps 1 and 3) onto the code of the X.2 stage, and states the readings taken where the draft is silent. The code applies the amendment only when the mapping is run with a committed amendment record that carries a `label_reading` section (`python tools/acquire_e4.py map --amendment audit/E4_AMENDMENT_1.json`). Without such a record the registered readings apply unchanged (R-4.4 for vintage labels, R-4.7 identical reference-quarter labels, R-X2.7 for locating the table).

All code places are in `src/uc_ext_official/e4_source.py` unless stated; all tests are in `tests/test_e4_amendment_1.py`. The tests use constructed workbooks only; the only texts taken from the real workbook are the three header texts and the sheet names that the draft itself quotes. Test results are development results (Python 3.12.3); the registered environment is Python 3.12.14 under `requirements.lock`.

## How the pieces fit

- `uc_e4.table.ReadLabel(text, year, month)` (the one change to the hashed analysis code): a vintage label handed over with the release month that the amendment reads in it. `parse_release_month` returns the carried reading (year and month checked for range), `_label_text` and `str()` give the text. The analysis code therefore never depends on the amendment. Tests: `test_read_label_is_read_as_the_reading_it_carries`, `test_read_labels_flow_through_build_tables_as_any_label`, `test_registered_reading_is_unchanged_for_texts_and_dates`.
- `validate_label_reading` and `load_label_reading`: the record's section, checked; `GateClosed` when it is malformed.
- `read_vintage_label` (rule A), `_read_by_place` (rule B), `_join_on_first_labels` (rule C).
- `table_parts(pieces, reading, date1904)`: the single construction of the table parts, used by `read_structure` (the mapping, which reads no numeric value) and by `read_level_tables` (X.4). It reads the labels (rules A and B, or the registered reading), pads the shorter parts (rule C) and returns the parts with the list of labels read (`label_readings`: sheet, column, text, year, month, rule).
- The registered `uc_e4.table.build_tables` then applies steps 1 to 5 to these parts unchanged: the join conditions of `join_parts` (vintage ranges that do not overlap, identical labels, which the padding has made identical), step 2 kinds, step 3, step 4 order and ties, step 5.

## Sentence by sentence

### A. Reading a vintage label (step 3)

| Draft sentence | Code | Test |
|---|---|---|
| "each run of spaces and line breaks in the text is replaced by one space and the ends are trimmed" | `normalise_label` | `test_rule_a_reads_every_form_the_amendment_describes` (line break, run of spaces and line breaks, trailing space) |
| "The label must then have this form: an English month name, in full or as its first three letters; a hyphen, with spaces allowed on either side; a year of two digits or of four digits; then, optionally, a price-base note (...); then, optionally, one code, "M1", "M2", "1st" or "QNA"." | `_RULE_A`, `_RULE_A_MONTHS`, `read_vintage_label` | `test_rule_a_reads_every_form_the_amendment_describes`, `test_rule_a_does_not_read_other_forms` |
| "A label of any other form does not parse, and the mapping stops at step 3 as registered." | `_read_labels` hands such a label to the registered step 3 as `_Unparsed` (neither text nor date), which stops at step 4.3 in the registered order; the reason of rule A is recorded in `amended_reading.rule_a_failures` and printed | `test_without_rule_b_the_three_texts_do_not_all_read`, `test_an_unread_label_stops_at_step_3_before_the_join_condition_as_registered` |
| "The release month is the month named, in the year given. A year of two digits yy is read as 19yy if yy is 61 or more and as 20yy otherwise" | `read_vintage_label(text, century_pivot=...)`; the pivot comes from the record (`rule_a.century_pivot`) | `test_rule_a_reads_every_form_the_amendment_describes` (Oct-61, Oct-60, Oct-00, Oct-99) |
| "The price-base note and the code describe the vintage and do not change its release month." | `read_vintage_label` reads the month from the month name and the year only | the same test (forms with note, code, both) |
| "In every record a vintage is identified by its label text with each run of spaces and line breaks replaced by one space." | `ReadLabel.text` is the normalised text; it is the vintage label in the availability table, in `table.parts[].vintage_labels` and in `label_readings` | `test_the_layout_maps_under_the_amendment_and_records_what_was_read_how`, `test_the_level_reader_reads_the_labels_and_joins_exactly_as_the_mapping` |

### B. Three labels read by place (step 3)

| Draft sentence | Code | Test |
|---|---|---|
| "These header cells are read as stated here and not by rule A" (the table of three places) | the record's `readings_by_place`; `_read_labels` applies `_read_by_place` at exactly those (sheet, column) places | `test_rule_b_reads_the_three_places_and_keeps_their_text` |
| "A reading by place is made only if the cell holds exactly the text listed and the labels in the columns immediately before and after it read, by rule A, as two months apart, so that the month read is the month between them" | `_read_by_place`: normalised texts compared; both neighbours read by `read_vintage_label`; months exactly two apart, listed month in the middle | `test_rule_b_stops_at_step_3_naming_the_place_when_a_condition_fails` (wrong text, neighbours not two months apart on either side, a neighbour that rule A does not read) |
| "If either condition fails, the mapping stops at step 3." | `Stop("4.3", "reading by place at sheet ..., column ...: ...")`, recorded as a stopped attempt | the same test; `test_a_failed_reading_by_place_is_a_recorded_stop_at_step_3`; `test_rule_b_entry_for_a_place_that_does_not_exist_stops` |
| "The label "Aug-98 [1995 prices]" (...) is not read by place: rule A reads it as written." | no entry in the record; the tie of release months is ordered by position (registered step 4) | `test_rule_b_text_in_another_column_or_sheet_is_read_by_rule_a`; the constructed tie in `test_the_layout_maps_under_the_amendment_and_records_what_was_read_how` |

### C. Joining the four sheets (step 1)

| Draft sentence | Code | Test |
|---|---|---|
| "They are joined, in the order of their vintage ranges, when their vintage ranges do not overlap, as registered, and when the reference-quarter labels of each part are, in the same order, the first labels of the reference-quarter labels of the longest part." | `_join_on_first_labels` (the condition), then the registered `join_parts` (ranges, order) | `test_rule_c_joins_parts_of_different_lengths_with_empty_padding_counted_as_empty`, `test_rule_c_parts_given_in_another_sheet_order_are_joined_in_the_order_of_their_ranges` |
| "This condition replaces the registered condition that the labels be identical." | the padding gives every part the longest part's labels, so `join_parts` is unchanged; without an amendment the registered condition applies | `test_without_an_amendment_the_registered_strict_rule_applies` |
| "The joined table has the reference quarters of the longest part." | padded `quarter_labels` are the longest part's | `test_rule_c_joins_parts_of_different_lengths_with_empty_padding_counted_as_empty` |
| "a reference quarter that has no row in that part is treated as an empty cell (...) and is counted as an empty cell in the availability table" | each added row holds `None` in every column of the part: kind `empty` for the registered code | the same test; the printed availability in `test_the_layout_maps_under_the_amendment_and_records_what_was_read_how` |
| "If the labels do not satisfy the condition, or the vintage ranges overlap, the mapping stops at step 1 as registered." | `Stop("4.1", ...)` naming the part, the row and the position; overlap by the registered `join_parts` | `test_rule_c_stops_at_step_1_naming_the_part_and_the_row` (not the first labels, a gap, a label written otherwise), `test_rule_c_keeps_the_registered_overlap_condition` |
| "By rules A and B the four parts hold vintages from September 1961 to November 1982, (...)" | not checked by the code (a statement about the real workbook); the mapping prints each part's release-month range so that it can be compared | (printed: `test_the_layout_maps_under_the_amendment_and_records_what_was_read_how`) |

One part alone is not changed (`test_one_part_alone_is_not_changed`).

### What does not change

| Draft sentence | Code | Test |
|---|---|---|
| "Steps 2, 4 and 5 and every other rule of section 4 apply as registered: a cell of kind other still stops the mapping (step 2); vintages are ordered by release month, vintages with the same release month by their position, and release months that do not increase in one direction stop the mapping (step 4)." | `uc_e4.table.build_tables`, unchanged | `test_what_does_not_change_a_cell_of_kind_other_and_the_order_rule_still_stop`; the tie in `test_the_layout_maps_under_the_amendment_and_records_what_was_read_how` |
| "The workbook already acquired is the one used (section 13)." | `map_structure` and `read_level_tables` read only the acquired file, checked against its record (`_raw`) | `test_the_level_reader_refuses_a_changed_amendment_record_or_workbook_or_label_list` |
| "If the mapping stops again, the stop is documented and settled by a further amendment before any value is read." | every attempt is recorded (`structure-attempt-<k>.json` and `.txt`, `structure-attempts.jsonl`) | `test_a_failed_reading_by_place_is_a_recorded_stop_at_step_3` |

## The record: schema of `label_reading`

The amendment record (for example `audit/E4_AMENDMENT_1.json`, committed before the mapping is run again) may hold any other fields; the X.2 stage reads only `label_reading`, which must have exactly these keys:

```json
{
  "label_reading": {
    "rule_a": {"century_pivot": 61, "codes": ["M1", "M2", "1st", "QNA"]},
    "readings_by_place": [
      {"sheet": "1961 - 1982", "column": "H", "text": "Sep-62 [1958 prices]", "release_month": "1962-03"},
      {"sheet": "1961 - 1982", "column": "CN", "text": "Mar-62 [1963 prices]", "release_month": "1969-03"},
      {"sheet": "1961 - 1982", "column": "GQ", "text": "Feb-772", "release_month": "1978-02"}
    ],
    "join": {"rule": "first_labels_of_longest_part"}
  }
}
```

- `rule_a.century_pivot`: an integer from 1 to 99; a two-digit year yy is 19yy when yy is at least the pivot, else 20yy.
- `rule_a.codes`: exactly the four codes of the draft, in any order. The grammar of rule A is fixed in the code (it is the text of the amendment); the list is checked against it so that the record states what is read, and a different list is refused.
- `readings_by_place`: a list; each entry has exactly `sheet`, `column` (capital letters), `text` (as written; compared after normalising the white space) and `release_month` (`YYYY-MM`). Two entries for one place are refused.
- `join.rule`: exactly `first_labels_of_longest_part`.

Any other shape is refused with `GateClosed` before an attempt is recorded (`test_a_malformed_label_reading_section_is_refused`). The mapping record of an attempt under the amendment adds: `label_reading` (the section as applied), `amended_reading` (per part: labels by form, release-month range, rows, last quarter; the readings by place applied with their neighbours; the join; any labels that rule A does not read), and, when the mapping completes, `label_readings` with `label_readings_sha256` (SHA-256 of the list as compact JSON with sorted keys). `read_level_tables` takes the amendment from `amendment.record` in the mapping record, checks that the committed file has the recorded SHA-256, rebuilds the parts with `table_parts` and requires the re-read `label_readings` and its hash to equal the recorded ones; the existing `kinds_sha256` check stays.

## Readings taken where the draft is silent

Each reading is the most literal one available; each is held by a test.

- **L-1 White space.** Quotation: "each run of spaces and line breaks". Choice: the space (U+0020), carriage return and line feed only; a tab or a non-breaking space is not normalised, so a label holding one does not parse. Test: `test_rule_a_does_not_read_other_forms` ("Jan-62\tM1").
- **L-2 Case.** Quotation: "an English month name, in full or as its first three letters". Choice: the month name is read without regard to case; the codes and the word "prices" are read as written. Tests: "oct-71" reads; "Jan-62 qna" and "[1954 Prices]" do not.
- **L-3 The hyphen.** Choice: the hyphen-minus (U+002D) only; an en dash does not parse. Test: "Jan–62".
- **L-4 Separators.** Choice: after normalising, one space before the price-base note and one before the code (the code on the next line becomes a space); the note precedes the code; at most one space on either side of the hyphen. Tests: "Jan-62 M1 [1954 prices]" and "Jan-62 M1 M2" do not parse.
- **L-5 Month names.** Choice: the twelve full names and their first three letters only ("Sept" is not accepted, unlike R-4.4). Test: "Sept-62".
- **L-6 Four-digit years.** Choice: 1000 to 2999, as the registered `_valid_year`.
- **L-7 Date-typed label cells.** The brief keeps the registered treatment: a date-typed cell is a date (R-X2.8); it is recorded in `label_readings` with rule `date`. Test: `test_rule_a_reads_only_texts_and_a_date_keeps_the_registered_treatment`.
- **L-8 Neighbours of a place.** Quotation: "the labels in the columns immediately before and after it". Choice: the sheet columns immediately before and after, which must be vintage columns of the same part (a separator column or the label column fails the condition); they are read by rule A even if one of them is itself listed as a place; "two months apart" in either direction, with the listed month the one between. Test: `test_rule_b_stops_at_step_3_naming_the_place_when_a_condition_fails`.
- **L-9 A place that is not a vintage label of the table** (an unknown sheet, a column outside the header, the label column): the cell cannot hold the listed text as a vintage label, so the mapping stops at step 3 naming the place. Test: `test_rule_b_entry_for_a_place_that_does_not_exist_stops`.
- **L-10 When the step 3 stops of rule B are found.** A failed reading by place stops when the parts are built, before steps 2 to 5 of `build_tables`. With several parts this keeps the registered order (R-4.9: step 1 already parses the labels); with a single part such a stop precedes a step 2 stop that would otherwise be reported first. The outcome (a stop and an amendment) is the same.
- **L-11 Rule C, ties for the longest part.** The first longest part in sheet order is the reference; another part of the same length must then have identical labels. Labels are compared as given (R-4.7).
- **L-12 Rule C after the labels.** The condition of rule C is checked only once every vintage label of every part reads, so that a label that does not read stops at step 3 first, as in the registered step 1 (R-4.9). Test: `test_an_unread_label_stops_at_step_3_before_the_join_condition_as_registered`.
- **L-13 Locating the table (R-X2.7).** The header row of a table is found as the nearest row above the reference quarters with a vintage label to the right; registered, a vintage label is a cell that parses under R-4.4. Labels such as "Oct-61" do not, so without a further reading the header rows of sheets whose labels all have two-digit years are not found. Under the amendment, a text header cell is a vintage label when rule A reads it (a date-typed cell as before). Without an amendment the registered test applies. Test: `test_the_layout_maps_under_the_amendment_and_records_what_was_read_how` (the registered attempt 1 on the same constructed workbook finds one sheet only and stops at step 3).
- **L-14 A cited record without `label_reading`.** The mapping then runs under the registered readings (an amendment that settles another stop), except after a stop at step 1 or 3, where it is refused before any attempt is recorded. Tests: `test_after_a_stop_at_step_3_an_amendment_record_without_label_reading_is_refused`, and the unchanged `test_a_stop_is_recorded_exits_non_zero_and_a_rerun_needs_a_committed_amendment` in `tests/test_e4_source_stages.py`.
- **L-15 Names in the file properties.** `creator` and `lastModifiedBy` are printed and recorded as "(name withheld)"; the title and notes check (R-X2.10) still reads them, and a conflict found in one of them is recorded with its text withheld. Tests: `test_creator_and_last_modified_by_are_neither_printed_nor_recorded`, `test_a_withheld_property_naming_another_release_is_recorded_without_its_text`.

## Limits

The real workbook has not been read by this code; its layout is known only from the draft's description. The tests show that a constructed workbook in that layout (four sheets of different row counts, every label form, the three places, a tie of two release months) maps under the amendment and that the level reader rebuilds the same tables; the real mapping is run on the research computer in the registered environment.
