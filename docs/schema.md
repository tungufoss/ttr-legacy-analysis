# Database schema

`ttr.db` is a SQLite database built by `scripts/build_db.py` from the
campaign workbook and the replay-PDF reference. Stored tables hold facts
only; all arithmetic lives in views (`scripts/views.sql`).

## Key concepts

- **run_id** — the backtracked unstacking order. The workbook's `id`
  column is one global sequence shared by tickets, employees, events,
  post-office and story cards: the order the dead letter office pile was
  taken apart. `run_id = 0` in the source marks cards found while going
  through a player's vault (no pile position); those are stored with
  `run_id NULL`. Story pause/stop cards carry game years, so any card's
  run position between two dated markers bounds *when it was retired*.
- **card_uid** — the proper legacy card code (`GP-14`, `CS-08`, ...).
  East Coast starter tickets carry no printed number, so they get
  synthesized codes `EC-01`..`EC-33` (alphabetical by route).

## Entity relationships

```mermaid
erDiagram
    players ||--o{ ticket_punches : "punches"
    players ||--o{ circus : "flyer rows"
    players ||--o{ timetable_cells : "cells"
    players ||--o{ bank_slips : "scores"
    players ||--o{ claims : "owns (mostly unknown)"
    players ||--o{ post_office : "vault"

    games ||--o{ bank_slips : "per game"

    run_order ||--o| tickets : "pile position"
    run_order ||--o| employees : "pile position"
    run_order ||--o| events : "pile position"
    run_order ||--o| post_office : "pile position"
    run_order ||--o| story_cards : "pile position"

    card_ref ||--o| tickets : "canonical card"
    card_ref ||--{ card_ref_capacity : "per-color capacity"
    card_ref ||--o| ticket_postcards : "postcard mapping"

    tickets ||--{ ticket_punches : "who punched"
    postcard_ref ||--o| ticket_postcards : "punchable postcards"

    claims ||--{ claim_spots : "7 scratch spots"
    circus ||--{ circus_stickers : "stickers"

    players {
        text color PK
        text company
        text gender
    }
    games {
        int year PK
        int seq
    }
    run_order {
        int id PK "run_id: unstack order"
        text card_type
    }
    card_ref {
        int ref_id PK
        text card_uid UK "EC-01.. synthesized"
        text card_code "printed code"
        text frontier
        text from_city
        text to_city
        int value
    }
    card_ref_capacity {
        int ref_id FK
        text color FK
        int capacity "1=postcard spot, 2=normal"
    }
    tickets {
        int ticket_id PK
        int run_id FK "NULL: vault or id collision"
        int ref_id FK
        text frontier "corrected"
        text frontier_original
        int value
        int active
        int postcard_card
    }
    ticket_punches {
        int ticket_id FK
        text color FK
        int punches
    }
    ticket_postcards {
        text card_uid PK
        int postcard_number
        text postcard_code "PC-xxx"
    }
    employees {
        int id PK
        int run_id FK
        text name
        int punches
        int active
        text origin
    }
    events {
        int id PK
        text name
        text origin
        int punched
        int active
    }
    post_office {
        int rowid_ PK
        int id FK "run_id; NULL = from vault"
        int card_number
        int read
        int punched
        text worth
        text vault FK
    }
    story_cards {
        int id PK
        text name
        int year "pause/stop markers"
        text location
    }
    claims {
        text card_code PK "CS-19..CS-24"
        text town
        text owner FK "only blue known"
    }
    claim_spots {
        text card_code FK
        int position
        int value "true value from reference"
        int revealed
    }
    circus {
        int rowid_ PK
        text player FK
        text type
        int valid
        int points
    }
    circus_stickers {
        int circus_row FK
        int position
        text color
    }
    timetable_cells {
        text player FK
        int row
        int col
        text city "NULL = not crossed off"
    }
    bank_slips {
        text player "incl 'missing' rows"
        int year FK
        int dollars
        int coins_in_hand
        int trains_bonus
        int ticket_value
        int miscalculation
    }
    postcard_ref {
        int card_number PK
        text title
        int punch_capacity
    }
```

## Views

| View | Purpose |
|---|---|
| `v_frontier_counts` | tickets tracked vs the canonical card list, per frontier |
| `v_circus_scores` | circus flyer points per player |
| `v_timetable_scores` | 10 points per completed timetable row/column |
| `v_claim_values` | true totals vs revealed state per claim card |
| `v_claim_earnings` | dollars actually collected from claims; NULL when the card was fully scratched post-campaign |
| `v_retirement_window` | earliest/latest game year a card can have been retired, from its run position between dated story markers |
| `v_ticket_retirement` | the same, joined to retired tickets |
| `v_ticket_rule_check` | punch-capacity rule violations (empty = consistent) |
| `v_scores` | bank slip scores per player per game |
| `v_campaign_totals` | campaign dollar totals per player |
