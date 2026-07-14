"""Build ttr.db from the campaign workbook + PDF-derived reference data.

Sources:
  data/raw/TtR Legacy.xlsx   -- the backtracked campaign records (main tables
                                only; the sheets' sanity-check helper blocks
                                are recreated as SQL views instead)
  data/reference/reference.json -- card facts extracted from the replay PDF
                                   (punch capacities, claim scratch values,
                                   punchable postcards/employees/events)

The workbook's `id` column is a single global sequence shared by the
Tickets, Employees, Events, PostOffice and Story sheets: the backtracked
dead-letter-office ordering. It becomes the run_order spine.
"""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "data" / "raw" / "TtR Legacy.xlsx"
REF = ROOT / "data" / "reference" / "reference.json"
DB = ROOT / "ttr.db"

COLORS = ["black", "blue", "green", "yellow", "red"]
COMPANIES = {
    "black": "New York Central System",
    "blue": "B&O",
    "green": "New Haven and Hartford",
    "yellow": "Erie",
    "red": "PRR",
}
# real-life player gender per color (no names tracked)
GENDERS = {
    "black": "male",
    "blue": "male",
    "green": "female",
    "yellow": "female",
    "red": "female",
}
GAME_YEARS = list(range(1865, 1899, 3)) + [1901]

# The workbook and the reference use different spellings for two cities.
def norm_city(name):
    if not isinstance(name, str):
        return name
    name = name.strip()
    return {"Montréal": "Montreal", "Québec": "Quebec"}.get(name, name)


def create_schema(con):
    con.executescript("""
    CREATE TABLE players (
        color TEXT PRIMARY KEY,
        company TEXT NOT NULL,
        gender TEXT NOT NULL CHECK (gender IN ('male','female'))
    );
    CREATE TABLE games (
        year INTEGER PRIMARY KEY,
        seq INTEGER NOT NULL
    );
    -- one row per card in the backtracked global ordering
    CREATE TABLE run_order (
        id INTEGER PRIMARY KEY,
        card_type TEXT NOT NULL CHECK (card_type IN
            ('ticket','employee','event','postoffice','story'))
    );
    -- canonical ticket cards from the replay reference (129 cards)
    CREATE TABLE card_ref (
        ref_id INTEGER PRIMARY KEY,
        card_uid TEXT NOT NULL UNIQUE,     -- unique code; EC cards get
                                           -- synthesized EC-01..EC-33
        card_code TEXT NOT NULL,           -- printed code; 'EC' shared by 33
        frontier TEXT NOT NULL,
        from_city TEXT NOT NULL,
        to_city TEXT NOT NULL,
        value INTEGER NOT NULL
    );
    -- per-color punch capacity: 1 = potential-postcard spot, 2 = normal
    CREATE TABLE card_ref_capacity (
        ref_id INTEGER NOT NULL REFERENCES card_ref(ref_id),
        color TEXT NOT NULL REFERENCES players(color),
        capacity INTEGER NOT NULL,
        PRIMARY KEY (ref_id, color)
    );
    CREATE TABLE tickets (
        ticket_id INTEGER PRIMARY KEY,     -- synthetic; source ids collide once
        run_id INTEGER REFERENCES run_order(id),  -- NULL for the duplicate
        ref_id INTEGER REFERENCES card_ref(ref_id),
        frontier TEXT NOT NULL,            -- corrected via card_ref
        frontier_original TEXT NOT NULL,   -- as recorded in the workbook
        from_city TEXT NOT NULL,
        to_city TEXT NOT NULL,
        value INTEGER NOT NULL,
        active INTEGER NOT NULL,
        postcard_card INTEGER,             -- post office card number earned
        valid TEXT,
        note TEXT
    );
    CREATE TABLE ticket_punches (
        ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id),
        color TEXT NOT NULL REFERENCES players(color),
        punches INTEGER NOT NULL,
        PRIMARY KEY (ticket_id, color)
    );
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,            -- source id; run slot may collide
        run_id INTEGER REFERENCES run_order(id),
        name TEXT NOT NULL,
        punches INTEGER NOT NULL,
        active INTEGER NOT NULL,
        origin TEXT
    );
    CREATE TABLE events (
        id INTEGER PRIMARY KEY REFERENCES run_order(id),
        name TEXT NOT NULL,
        origin TEXT,
        punched INTEGER NOT NULL,
        active INTEGER NOT NULL
    );
    -- post office cards; id 0 in the sheet = found in a company vault,
    -- never entered the dead letter office (stored as NULL here)
    CREATE TABLE post_office (
        rowid_ INTEGER PRIMARY KEY,
        id INTEGER REFERENCES run_order(id),
        card_number INTEGER NOT NULL,
        read INTEGER NOT NULL,
        punched INTEGER,
        worth TEXT,                        -- numeric or 'piggyback'
        vault TEXT REFERENCES players(color)
    );
    CREATE TABLE story_cards (
        id INTEGER PRIMARY KEY REFERENCES run_order(id),
        name TEXT NOT NULL,
        year INTEGER,
        location TEXT
    );
    -- claim (scratch) cards: 6 cards, 5 players; only blue's is attributed
    CREATE TABLE claims (
        card_code TEXT PRIMARY KEY,        -- CS-19..CS-24
        town TEXT NOT NULL,
        owner TEXT REFERENCES players(color)  -- NULL = unknown or unowned extra
    );
    CREATE TABLE claim_spots (
        card_code TEXT NOT NULL REFERENCES claims(card_code),
        position INTEGER NOT NULL,         -- 1..7
        value INTEGER NOT NULL,            -- true value from reference
        revealed INTEGER NOT NULL,         -- scratched off during play
        PRIMARY KEY (card_code, position)
    );
    CREATE TABLE circus (
        rowid_ INTEGER PRIMARY KEY,
        player TEXT NOT NULL REFERENCES players(color),
        type TEXT NOT NULL,                -- 8/16/32/64 or 'sanctuary'
        valid INTEGER NOT NULL,
        points INTEGER NOT NULL
    );
    CREATE TABLE circus_stickers (
        circus_row INTEGER NOT NULL REFERENCES circus(rowid_),
        position INTEGER NOT NULL,
        color TEXT NOT NULL,
        PRIMARY KEY (circus_row, position)
    );
    CREATE TABLE timetable_cells (
        player TEXT NOT NULL REFERENCES players(color),
        row INTEGER NOT NULL,
        col INTEGER NOT NULL,
        city TEXT,                         -- NULL = never crossed off
        PRIMARY KEY (player, row, col)
    );
    CREATE TABLE bank_slips (
        player TEXT NOT NULL,              -- includes 'missing' placeholder rows
        year INTEGER NOT NULL REFERENCES games(year),
        dollars INTEGER NOT NULL,
        coins_in_hand INTEGER,
        trains_bonus INTEGER,
        ticket_value INTEGER,
        miscalculation INTEGER,
        PRIMARY KEY (player, year)
    );
    CREATE TABLE postcard_ref (
        card_number INTEGER PRIMARY KEY,   -- 102 for PC-102 etc.
        title TEXT NOT NULL,
        punch_capacity INTEGER NOT NULL
    );
    CREATE TABLE employee_ref (
        card_code TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        punch_capacity INTEGER NOT NULL
    );
    CREATE TABLE event_ref (
        card_code TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        punch_capacity INTEGER NOT NULL
    );
    -- fixed mapping: which postcard each potential-postcard ticket leads to
    CREATE TABLE ticket_postcards (
        card_uid TEXT PRIMARY KEY REFERENCES card_ref(card_uid),
        postcard_number INTEGER NOT NULL,
        postcard_code TEXT NOT NULL        -- 'PC-123'
    );
    """)


KNOWN_CITIES = [
    "Vancouver", "Calgary", "Regina", "Winnipeg", "Buffalo", "Detroit", "Quebec", "Bangor",
    "Seattle", "Helena", "Miles City", "Fargo", "Duluth", "Chicago", "Montreal", "Boston",
    "Portland", "Spokane", "Salt Lake City", "St. Paul", "Davenport", "Lewisburg", "Albany", "New York",
    "San Francisco", "Sacramento", "Cemetery City", "Cheyenne", "Omaha", "Cincinnati", "Pittsburgh", "Philadelphia",
    "Pacific Haven", "Phoenix", "Denver", "Kansas City", "St. Louis", "Knoxville", "Baltimore", "Norfolk",
    "Nuevos Angeles", "Santa Fe", "Dodge City", "Oklahoma City", "Nashville", "Atlanta", "Charlotte", "Charleston",
    "Baja", "Hermosillo", "El Paso", "Dallas", "Little Rock", "Mobile", "Savannah", "Jacksonville",
    "Chihuahua", "Monterrey", "San Antonio", "Houston", "New Orleans", "Tampa", "Miami",
]


def split_route(words):
    """Split the PDF's route word list into (from_city, to_city)."""
    text = " ".join(words)
    for city in sorted(KNOWN_CITIES, key=len, reverse=True):
        if text.startswith(city + " "):
            rest = text[len(city):].strip()
            if rest in KNOWN_CITIES:
                return city, rest
    raise ValueError(f"cannot split route: {text!r}")


def load_players_and_games(con):
    for color, company in COMPANIES.items():
        con.execute("INSERT INTO players VALUES (?,?,?)",
                    (color, company, GENDERS[color]))
    for seq, year in enumerate(GAME_YEARS, start=1):
        con.execute("INSERT INTO games VALUES (?,?)", (year, seq))


def load_reference(con, ref):
    ec_counter = 0
    for i, t in enumerate(ref["tickets"], start=1):
        from_city, to_city = split_route(t["route_words"])
        frontier = "Initial" if t["frontier"].startswith("East Coast") else t["frontier"]
        if t["card_code"] == "EC":
            # EC cards carry no individual printed number; synthesize one
            # following the reference list order (alphabetical by route)
            ec_counter += 1
            card_uid = f"EC-{ec_counter:02d}"
        else:
            card_uid = t["card_code"]
        con.execute(
            "INSERT INTO card_ref VALUES (?,?,?,?,?,?,?)",
            (i, card_uid, t["card_code"], frontier, from_city, to_city, t["value"]),
        )
        for color, cap in t["punch_capacity"].items():
            con.execute("INSERT INTO card_ref_capacity VALUES (?,?,?)", (i, color, cap))

    for pc in ref["post_cards"]:
        num = int(pc["card_code"].split("-")[1])
        con.execute("INSERT INTO postcard_ref VALUES (?,?,?)",
                    (num, pc["title"], pc["punch_capacity"]))
    for e in ref["employees"]:
        con.execute("INSERT INTO employee_ref VALUES (?,?,?)",
                    (e["card_code"], e["title"], e["punch_capacity"]))
    for e in ref["events"]:
        con.execute("INSERT INTO event_ref VALUES (?,?,?)",
                    (e["card_code"], e["title"], e["punch_capacity"]))


def load_workbook(con, ref):
    xl = pd.ExcelFile(XLSX)

    # --- tickets (main table = first 14 columns) ---
    df = xl.parse("Tickets").iloc[:, :15]
    ref_lookup = {}
    for row in con.execute("SELECT ref_id, from_city, to_city, value FROM card_ref"):
        key = (frozenset([row[1], row[2]]), row[3])
        ref_lookup[key] = row[0]

    seen_run_ids = set()
    ticket_pk = 0
    for _, r in df.iterrows():
        if pd.isna(r["id"]):
            continue
        ticket_pk += 1
        run_id = int(r["id"])
        note = None if pd.isna(r.get("note")) else str(r.get("note"))
        if run_id in seen_run_ids:
            # source data assigns the same dead-letter position twice
            # (known collision: id 105); keep the row, drop the position
            print(f"WARNING: duplicate run id {run_id} "
                  f"({r['From']} - {r['To']}); stored with run_id NULL")
            note = f"[run id collision: source id {run_id}] " + (note or "")
            run_id = None
        else:
            seen_run_ids.add(run_id)
            con.execute("INSERT INTO run_order VALUES (?, 'ticket')", (run_id,))
        from_city, to_city = norm_city(r["From"]), norm_city(r["To"])
        key = (frozenset([from_city, to_city]), int(r["Dollars"]))
        rid = ref_lookup.get(key)
        frontier = r["Box"]
        if rid is not None:
            frontier = con.execute(
                "SELECT frontier FROM card_ref WHERE ref_id=?", (rid,)).fetchone()[0]
        postcard = int(r["Postcard"]) if r["Postcard"] and int(r["Postcard"]) > 0 else None
        con.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_pk, run_id, rid, frontier, r["Box"], from_city, to_city,
             int(r["Dollars"]), int(r["Active"]), postcard, r.get("valid"), note),
        )
        for color, col in zip(COLORS, ["Black", "Blue", "Green", "Yellow", "Red"]):
            con.execute("INSERT INTO ticket_punches VALUES (?,?,?)",
                        (ticket_pk, color, int(r[col])))
        # verify the sheet's Punches helper column before dropping it
        assert int(r["Punches"]) == sum(int(r[c]) for c in ["Black", "Blue", "Green", "Yellow", "Red"]), \
            f"ticket {ticket_pk}: Punches != sum of colors"

    # --- ticket -> postcard mapping (fixed by the game; the workbook
    # records the postcard number on every potential-postcard ticket) ---
    con.execute("""
        INSERT INTO ticket_postcards
        SELECT r.card_uid, t.postcard_card, 'PC-' || t.postcard_card
        FROM tickets t JOIN card_ref r ON r.ref_id = t.ref_id
        WHERE t.postcard_card IS NOT NULL
    """)

    # --- employees ---
    df = xl.parse("Employees")
    for _, r in df.iterrows():
        eid = int(r["id"])
        run_id = eid
        if run_id in seen_run_ids:
            print(f"WARNING: duplicate run id {run_id} "
                  f"(employee {r['Name']}); stored with run_id NULL")
            run_id = None
        else:
            seen_run_ids.add(run_id)
            con.execute("INSERT INTO run_order VALUES (?, 'employee')", (run_id,))
        con.execute("INSERT INTO employees VALUES (?,?,?,?,?,?)",
                    (eid, run_id, r["Name"], int(r["Punches"]), int(r["Active"]),
                     str(r["Origin"])))

    # --- events ---
    df = xl.parse("Events")
    for _, r in df.iterrows():
        con.execute("INSERT INTO run_order VALUES (?, 'event')", (int(r["id"]),))
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                    (int(r["id"]), r["Name"], str(r["Origin"]), int(r["Punched"]),
                     int(r["Active"])))

    # --- post office ---
    df = xl.parse("PostOffice")
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        oid = int(r["id"])
        run_id = None
        if oid > 0:
            con.execute("INSERT INTO run_order VALUES (?, 'postoffice')", (oid,))
            run_id = oid
        worth = None if pd.isna(r["Worth"]) else str(r["Worth"])
        vault = None if pd.isna(r["Vault"]) else str(r["Vault"]).strip().lower()
        punched = None if pd.isna(r["Punched"]) else int(r["Punched"])
        con.execute("INSERT INTO post_office VALUES (?,?,?,?,?,?,?)",
                    (i, run_id, int(r["Card"]), int(r["Read"]), punched, worth, vault))

    # --- story cards ---
    df = xl.parse("Story")
    for _, r in df.iterrows():
        con.execute("INSERT INTO run_order VALUES (?, 'story')", (int(r["id"]),))
        year = None if pd.isna(r["Year"]) else int(r["Year"])
        loc = None if pd.isna(r["location"]) else str(r["location"])
        con.execute("INSERT INTO story_cards VALUES (?,?,?,?)",
                    (int(r["id"]), str(r["Name"]), year, loc))

    # --- claims: reference gives the truth; workbook gives owner + revealed state ---
    claim_ref = {c["town"]: c for c in ref["claims"] if c["card_code"].startswith("CS-")}
    df = xl.parse("Claims")
    for _, r in df.iterrows():
        town = norm_city(r["Claim"])
        cref = claim_ref.get(town) or claim_ref.get(r["Claim"])
        if cref is None:
            raise ValueError(f"claim town {r['Claim']!r} not in reference")
        owner = str(r["Player"]).strip().lower()
        owner = owner if owner in COLORS else None
        con.execute("INSERT INTO claims VALUES (?,?,?)",
                    (cref["card_code"], cref["town"], owner))
        for pos in range(1, 8):
            observed = r[f"Value {pos}"]
            observed = None if pd.isna(observed) else int(observed)
            true_val = cref["values"][pos - 1]
            revealed = 1 if observed not in (None, 0) else 0
            if revealed and observed != true_val:
                raise ValueError(
                    f"claim {cref['card_code']} spot {pos}: sheet says {observed}, "
                    f"reference says {true_val}")
            con.execute("INSERT INTO claim_spots VALUES (?,?,?,?)",
                        (cref["card_code"], pos, true_val, revealed))

    # --- circus (main table = first 10 columns) ---
    df = xl.parse("Circus").iloc[:, :10]
    df = df[df["player"].notna()]
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        con.execute("INSERT INTO circus VALUES (?,?,?,?,?)",
                    (i, str(r["player"]).lower(), str(r["type"]),
                     int(r["valid"]), int(r["points"])))
        for pos in range(1, 7):
            sticker = r.get(f"sticker {pos}")
            if isinstance(sticker, str) and sticker.strip():
                con.execute("INSERT INTO circus_stickers VALUES (?,?,?)",
                            (i, pos, sticker.strip().lower()))

    # --- timetable (main block: row, column 1..8, player) ---
    raw = xl.parse("timetable", header=None)
    header_row = None
    for i in range(len(raw)):
        if str(raw.iloc[i, 0]).strip() == "row":
            header_row = i
            break
    for i in range(header_row + 1, len(raw)):
        r = raw.iloc[i]
        if pd.isna(r[0]) or pd.isna(r[9]):
            continue
        player = str(r[9]).strip().lower()
        if player not in COLORS and player != "dummy":
            continue
        if player == "dummy":
            continue  # unused placeholder card
        row_no = int(r[0])
        for col in range(1, 9):
            city = r[col]
            city = None if pd.isna(city) else norm_city(str(city).strip())
            con.execute("INSERT INTO timetable_cells VALUES (?,?,?,?)",
                        (player, row_no, col, city))

    # --- bank slips ---
    df = xl.parse("Bankslips")
    for _, r in df.iterrows():
        def opt(v):
            return None if pd.isna(v) else int(v)
        con.execute("INSERT INTO bank_slips VALUES (?,?,?,?,?,?,?)",
                    (str(r["player"]).strip().lower(), int(r["game"]), int(r["dollars"]),
                     opt(r["Coins in hand"]), opt(r["Bonus for trains remaining"]),
                     opt(r["Total ticket value"]), opt(r["Miscalculation"])))


def main():
    DB.unlink(missing_ok=True)
    ref = json.loads(REF.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    create_schema(con)
    load_players_and_games(con)
    load_reference(con, ref)
    load_workbook(con, ref)
    con.commit()

    views_sql = (Path(__file__).parent / "views.sql")
    if views_sql.exists():
        con.executescript(views_sql.read_text(encoding="utf-8"))
        con.commit()

    for table in ["run_order", "card_ref", "tickets", "ticket_punches", "employees",
                  "events", "post_office", "story_cards", "claims", "claim_spots",
                  "circus", "circus_stickers", "timetable_cells", "bank_slips",
                  "postcard_ref", "employee_ref", "event_ref"]:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {n}")
    con.close()


if __name__ == "__main__":
    main()
