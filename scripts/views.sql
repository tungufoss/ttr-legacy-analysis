-- Views recreating the workbook's sanity-check helper blocks, plus
-- derived analytics. All arithmetic lives here, not in stored data.

-- Tickets per frontier, checked against the canonical card list.
CREATE VIEW v_frontier_counts AS
SELECT
    r.frontier,
    COUNT(DISTINCT r.ref_id)                          AS cards_in_game,
    COUNT(t.ticket_id)                                AS cards_tracked,
    COUNT(DISTINCT r.ref_id) - COUNT(t.ticket_id)     AS missing
FROM card_ref r
LEFT JOIN tickets t ON t.ref_id = r.ref_id
GROUP BY r.frontier;

-- Circus scoring per player (the sheet's right-hand helper block).
CREATE VIEW v_circus_scores AS
SELECT player, SUM(points) AS total_points
FROM circus
GROUP BY player;

-- Timetable scoring: 10 points per fully crossed-off row or column.
CREATE VIEW v_timetable_scores AS
WITH row_scores AS (
    SELECT player, row, MIN(city IS NOT NULL) AS complete
    FROM timetable_cells GROUP BY player, row
), col_scores AS (
    SELECT player, col, MIN(city IS NOT NULL) AS complete
    FROM timetable_cells GROUP BY player, col
)
SELECT
    p.color AS player,
    10 * (SELECT COALESCE(SUM(complete),0) FROM row_scores WHERE player = p.color)
  + 10 * (SELECT COALESCE(SUM(complete),0) FROM col_scores WHERE player = p.color)
    AS total_points
FROM players p;

-- Claim card totals: true total (all 7 spots, from reference) vs the
-- revealed state observed after the campaign.
CREATE VIEW v_claim_values AS
SELECT
    c.card_code,
    c.town,
    c.owner,
    SUM(s.value)                                    AS true_total,
    SUM(CASE WHEN s.revealed THEN s.value END)      AS revealed_total,
    SUM(s.revealed)                                 AS spots_revealed
FROM claims c
JOIN claim_spots s USING (card_code)
GROUP BY c.card_code;

-- Claim earnings actually collected during play.
-- On partially-scratched cards, the scratched spots are exactly the claims
-- collected, so their sum is the card's true earnings. Fully-scratched
-- cards (all 7) were opened out of curiosity after the campaign - play
-- scratches can no longer be told apart, so earnings are unknown (NULL).
CREATE VIEW v_claim_earnings AS
SELECT
    card_code,
    town,
    owner,
    CASE WHEN spots_revealed < 7
         THEN COALESCE(revealed_total, 0)
    END AS earned_dollars,
    spots_revealed < 7 AS earnings_known
FROM v_claim_values;

-- Retirement window for every retired card in the dead letter office.
-- Story pause/stop cards carry years; a card's run position between two
-- dated markers bounds when it was retired. Higher run ids sit deeper in
-- the pile (earlier games), so:
--   earliest_year = year of the nearest dated marker with a HIGHER id
--   latest_year   = year of the nearest dated marker with a LOWER id
CREATE VIEW v_retirement_window AS
SELECT
    d.id AS run_id,
    d.card_type,
    (SELECT s.year FROM story_cards s
      WHERE s.year IS NOT NULL AND s.id > d.id
      ORDER BY s.id ASC LIMIT 1)  AS earliest_year,
    (SELECT s.year FROM story_cards s
      WHERE s.year IS NOT NULL AND s.id < d.id
      ORDER BY s.id DESC LIMIT 1) AS latest_year
FROM run_order d;

-- Ticket-level retirement inference (retired tickets only).
CREATE VIEW v_ticket_retirement AS
SELECT
    t.ticket_id,
    r.card_code,
    t.frontier,
    t.from_city,
    t.to_city,
    w.earliest_year,
    w.latest_year
FROM tickets t
JOIN v_retirement_window w ON w.run_id = t.run_id
LEFT JOIN card_ref r ON r.ref_id = t.ref_id
WHERE t.active = 0;

-- Game-rule consistency checks. Empty result = data consistent.
-- postcard spots (capacity 1): retired on first punch by anyone
-- normal spots (capacity 2): retired when one color reaches 2 punches
CREATE VIEW v_ticket_rule_check AS
SELECT
    t.ticket_id,
    r.card_code,
    t.from_city,
    t.to_city,
    p.color,
    p.punches,
    c.capacity,
    CASE
        WHEN p.punches > c.capacity THEN 'punches exceed capacity'
        WHEN t.active = 1 AND p.punches = 2 THEN 'double-punched but still active'
    END AS violation
FROM tickets t
JOIN ticket_punches p ON p.ticket_id = t.ticket_id
JOIN card_ref r ON r.ref_id = t.ref_id
JOIN card_ref_capacity c ON c.ref_id = t.ref_id AND c.color = p.color
WHERE violation IS NOT NULL;

-- Final scores per player per game, from the bank slips.
CREATE VIEW v_scores AS
SELECT player, year, dollars,
       coins_in_hand, trains_bonus, ticket_value, miscalculation
FROM bank_slips
WHERE player IN (SELECT color FROM players)
ORDER BY year, dollars DESC;

-- Campaign totals per player.
CREATE VIEW v_campaign_totals AS
SELECT player, SUM(dollars) AS total_dollars, COUNT(*) AS games_played
FROM bank_slips
WHERE player IN (SELECT color FROM players)
GROUP BY player
ORDER BY total_dollars DESC;
