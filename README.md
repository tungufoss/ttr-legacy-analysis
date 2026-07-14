# ttr-legacy-analysis

Data analysis of a *Ticket to Ride Legacy: Legends of the West* campaign, tracked
across a shared spreadsheet during play. This repo holds the cleaned data and
the scripts used to get there.

## Structure

```
data/
  raw/         # untouched exports from the tracking spreadsheet
  reference/   # canonical card_id -> frontier/route/value lookup table
  clean/       # cleaned data, joined against the reference table
scripts/
  clean_tickets.py   # builds data/clean/tickets_clean.csv
```

## Data quality fixes applied

The original spreadsheet's "Tickets" sheet had a few issues that this
pipeline corrects:

1. **Frontier labels were swapped for some regions.** The "Box" column
   confused California/Cascadia and Open Range/Great Plains for a subset of
   rows. Since each pair's ticket counts happened to be close (14 vs 15),
   this went unnoticed in aggregate totals. Fixed by joining each ticket's
   (from, to, value) against the canonical card reference to derive the
   correct frontier — 35 of 128 rows had their frontier corrected.
2. **Accented city name mismatch.** The raw data uses French accented
   spellings ("Montréal", "Québec") while the reference table uses
   unaccented English spellings ("Montreal", "Quebec"). Normalized before
   joining.
3. **A runaway formula bloated the source file.** The original `.ods` had a
   formula filled down to the sheet's maximum row (1,048,576 rows), producing
   a ~7.7MB file and freezing Excel on open. `data/raw/tickets.csv` is
   already trimmed to the 128 real ticket rows.

## Reference table

`data/reference/card_ids.csv` maps each canonical card identifier (e.g.
`GP-14`, `HW-13`, `EC`) to its frontier, route, and point value. It was built
from the game's own card list, used here only as a lookup key for data
cleaning — not reproduced as a rulebook or document.

## Running the cleaning pipeline

```
python scripts/clean_tickets.py
```
