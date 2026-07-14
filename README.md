# Ticket to Ride Legacy — Data Dive

A data dive into our *Ticket to Ride Legacy: Legends of the West* campaign.
After the campaign ended, the entire game state was backtracked by hand:
every ticket, employee, event, post card and story card still in the
storeroom, post office and company vaults — and the full dead letter office
pile, unstacked card by card. This repo turns that record into a queryable
SQLite database and digs into what it reveals.

## The database

Everything lives in `ttr.db`, rebuilt reproducibly from the raw workbook.
The full schema is documented with an ER diagram in
[docs/schema.qmd](docs/schema.qmd).

```
data/
  raw/TtR Legacy.xlsx        # the hand-backtracked campaign record
  reference/reference.json   # card facts extracted from the replay checklist PDF
scripts/
  extract_reference.py       # PDF -> reference.json
  build_db.py                # xlsx + reference.json -> ttr.db
  views.sql                  # derived views (all arithmetic lives here)
docs/schema.qmd            # ER diagram (mermaid) + view catalog
ttr.db                       # the database
index.qmd, _quarto.yml       # Quarto report (ggplot dashboard)
```

Rebuild the database with `python scripts/build_db.py`, render the
report with `quarto render`.

### The run_order spine

The workbook's `id` column is a **run id**: a single global sequence
shared across the Tickets, Employees, Events, PostOffice and Story
sheets — the order the dead letter office pile was unstacked during the
backtrack (`run id 0` = found in a player's vault, no pile position). It
becomes the `run_order` table, and since story pause/stop cards carry
game years, any card's position between two dated markers bounds *when
it was retired* (`v_retirement_window`, `v_ticket_retirement`).

Proper legacy card codes live in `card_ref.card_uid` (`GP-14`, `CS-08`,
…; the unnumbered East Coast starters get synthesized `EC-01`..`EC-33`),
and `ticket_postcards` maps all 42 potential-postcard tickets to their
postcard (`PC-101`..`PC-142`) — the workbook had the complete mapping.

### Main tables

| Table | Contents |
|---|---|
| `tickets` + `ticket_punches` | all 129 ticket cards, punches per player |
| `card_ref` + `card_ref_capacity` | canonical card list; per-color punch capacity (1 = potential postcard, 2 = normal) |
| `employees`, `events`, `post_office`, `story_cards` | the other card types |
| `claims` + `claim_spots` | scratch cards: true values from reference, revealed state from play |
| `circus` + `circus_stickers`, `timetable_cells`, `bank_slips` | endgame scoring components |
| `postcard_ref`, `employee_ref`, `event_ref` | punchable-card reference from the PDF |

The workbook's helper formula blocks (COUNTIFS checks etc.) are deliberately
not stored — they are recreated as SQL views (`v_frontier_counts`,
`v_circus_scores`, `v_timetable_scores`, `v_claim_values`, …), so any
mismatch points at a data problem rather than a stale formula.

## What the dive turned up

1. **The backtrack is complete and consistent.** All 129 ticket cards are
   accounted for (`v_frontier_counts` shows zero missing per frontier), and
   `v_ticket_rule_check` — which tests every punch against each card's
   per-color capacity from the reference — returns **zero violations**.
2. **Every claim card totals exactly 98.** The six scratch cards
   (CS-19..CS-24) all sum to the same 98 dollars — the values are shuffled
   between spots, but no claim card is better than another.
3. **Every revealed scratch value matched the reference.** The build
   cross-checks each value scratched off during play against the replay
   PDF's card list; all 25 revealed spots matched.
4. **Swapped frontier labels.** An earlier tracking sheet had
   California ↔ Cascadia and Open Range ↔ Great Plains confused on ~35
   rows. Each swapped pair happened to have near-equal card counts
   (14 + 15), so every aggregate total looked fine — invisible until
   individual tickets were joined against the canonical card list.
5. **The million-row formula.** The original `.ods` tracking file had a
   formula filled down to the spreadsheet's maximum row — 1,048,576 rows
   each computing `0`. The file ballooned to 7.7MB, froze Excel for hours,
   and was rejected by Google Sheets as "too large to import". Real data:
   129 rows.

Plus from the endgame data: every claim card hides the same 98$ total;
Portland's claim card was never used at all (0$ collected); black won
the campaign (1152$) after trading the lead with yellow twice, while
blue held 5th place from 1865 to 1898 without interruption.

Lesson so far: totals that add up can still be wrong, and the data you
track during a game night is as messy as any production dataset.

## The report

`index.qmd` is a Quarto website with the ggplot dashboard: score
progression per game and cumulative, rank changes, scoring-component
breakdowns, ticket punches, claim earnings, and a gender comparison
(black/blue are played by men, green/yellow/red by women; no names
tracked). Render with `quarto render`, output lands in `_site/`.

## Open questions

- **Deck id collisions.** Source id `105` is assigned to two tickets
  (CA-13 and GP-09), and id `128` to both a ticket (GP-07) and the
  Financier employee. One of each pair is misnumbered; the affected rows
  are stored with `deck_id NULL` and a note.
- **Claim ownership.** Only Blue's claim card (CS-24 Helena) is
  attributed. Of the remaining five, four belong to black/green/yellow/red
  in some unknown assignment and one is the unowned extra.
- **Bankslips `missing` rows.** Twelve rows with player `missing` and
  round dollar values (30..140) — meaning to be confirmed.

## Reference data

`data/reference/reference.json` holds card facts (codes, routes, values,
punch capacities, scratch-card values) extracted from Maddes' replay
checklist PDF (BoardGameGeek). Only game facts are extracted, used as join
keys and validation constraints — no rules text or game content is
reproduced.
