# Ticket to Ride Legacy — Data Dive

A data dive into our *Ticket to Ride Legacy: Legends of the West* campaign.
Every ticket claimed over the campaign was tracked in a shared spreadsheet;
this repo digs into that data — cleaning it up, checking it against the
game's own card list, and (along the way) uncovering a few surprises hiding
in the tracking sheet itself.

## The data

128 ticket claims across 9 frontiers, recorded during play: who completed
which route, for how many dollars, and whether it earned a postcard.

```
data/
  raw/         # untouched exports from the tracking spreadsheet
  reference/   # canonical card_id -> frontier/route/value lookup table
  clean/       # cleaned data, joined against the reference table
scripts/
  clean_tickets.py   # builds data/clean/tickets_clean.csv
```

Each ticket in the clean data carries its canonical card identifier
(`GP-14`, `HW-13`, `EC`, ...), so analyses can join on a stable key instead
of free-text route names.

## What the dive turned up

Before any analysis could happen, the tracking sheet itself had stories to
tell:

1. **Swapped frontier labels.** The sheet's "Box" column confused
   California ↔ Cascadia and Open Range ↔ Great Plains on a subset of rows.
   Each swapped pair happened to sum to the same ticket count (14 + 15), so
   every aggregate total looked perfectly fine — the error was invisible
   until individual tickets were checked against the canonical card list.
   35 of 128 rows needed their frontier corrected.
2. **Two spellings of the same city.** The ticket data says "Montréal" and
   "Québec"; the card list says "Montreal" and "Quebec". Twelve tickets
   silently failed to match until the spellings were normalized.
3. **The million-row formula.** The original `.ods` tracking file had a
   formula filled down to the spreadsheet's maximum row — 1,048,576 rows of
   empty cells each computing `0`. The file ballooned to 7.7MB, froze Excel
   for hours, and was rejected by Google Sheets as "too large to import".
   The real data: 128 rows.

Lesson of the dive so far: totals that add up can still be wrong, and the
data you track during a game night is as messy as any production dataset.

## Reference table

`data/reference/card_ids.csv` maps each canonical card identifier to its
frontier, route, and dollar value. It was built from the game's own card
list and is used purely as a join key for validation — it is not a
reproduction of any game material.

## Reproducing the clean data

```
python scripts/clean_tickets.py
```

Prints a summary of how many rows were corrected and writes
`data/clean/tickets_clean.csv`.
