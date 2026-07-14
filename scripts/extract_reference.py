"""Extract reference facts from the TTRL-LOTW-Replay checklist PDF (Maddes/BGG).

Produces data/reference/reference.json with:
  - tickets: card code, frontier, route, value, per-color punch capacity
    (single checkbox = potential postcard ticket, double = normal)
  - claims: scratch-card values for CS-19..CS-24 and SM-15
  - postcards: PC-1xx punchable postcards with titles and punch capacity
  - employees / events: punchable cards with capacities

Only game facts (codes, numbers, capacities) are extracted — no rules text.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import fitz

PDF = Path(r"C:\Users\hbi3\Downloads\TTRL-LOTW-Replay.pdf")
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "reference.json"

COLORS = ["black", "blue", "green", "yellow", "red"]


def page_lines(page, y_tol=3):
    """Cluster words into visual lines by y position, sorted left to right."""
    lines = defaultdict(list)
    for w in page.get_text("words"):
        placed = False
        for y in list(lines):
            if abs(w[1] - y) <= y_tol:
                lines[y].append(w)
                placed = True
                break
        if not placed:
            lines[w[1]].append(w)
    out = []
    for y in sorted(lines):
        ws = sorted(lines[y], key=lambda x: x[0])
        out.append(ws)
    return out


def extract_tickets(doc):
    """Ticket tables: rows of [☐ CODE, from..., to..., $, 5 checkbox groups]."""
    tickets = []
    frontier = None
    code_re = re.compile(r"^(?:[A-Z]{2}-\d{2}|EC)$")
    for pno in range(len(doc)):
        text = doc[pno].get_text()
        if "Tickets - " not in text:
            continue
        for ws in page_lines(doc[pno]):
            joined = " ".join(w[4] for w in ws)
            m = re.search(r"Tickets - (.+)", joined)
            if m:
                # the color column headers can cluster onto the section
                # header line; strip them from the frontier name
                frontier = m.group(1).strip()
                for color in COLORS:
                    frontier = re.sub(rf"\b{color}\b", "", frontier)
                frontier = frontier.strip()
                continue
            tokens = [w[4] for w in ws]
            codes = [t for t in tokens if code_re.match(t)]
            if not codes or frontier is None:
                continue
            code = codes[0]
            boxes = [t for t in tokens if set(t) == {"☐"}]
            # first box is the retire checkbox; the last five are color groups
            if len(boxes) < 6:
                continue
            groups = boxes[-5:]
            nums = [t for t in tokens if t.isdigit()]
            if not nums:
                continue
            value = int(nums[-1])
            words = [t for t in tokens if not set(t) == {"☐"} and t != code and not t.isdigit()]
            tickets.append({
                "card_code": code,
                "frontier": frontier,
                "route_words": words,  # from+to words; city split resolved in build_db
                "value": value,
                "punch_capacity": {c: len(g) for c, g in zip(COLORS, groups)},
            })
    return tickets


def extract_claims(doc):
    """Scratch cards: CS-19..CS-24 (7 values) and SM-15 (5 values).

    Each card is a small block: code word, a row of values ~6pt below it
    (left to right = scratch spots 1..7), and the town name below the code.
    """
    claims = []
    for pno in range(len(doc)):
        if "Scratch Cards" not in doc[pno].get_text():
            continue
        words = doc[pno].get_text("words")
        for w in words:
            if not re.match(r"^(CS-(19|2\d)|SM-15)$", w[4]):
                continue
            code, y = w[4], w[1]
            # CS cards put values ~6pt below the code; SM-15 sits in a
            # separate block with its value row ~27pt below
            y_max = 50 if code == "SM-15" else 12
            values = sorted(
                (x for x in words if x[4].isdigit() and 0 < x[1] - y < y_max),
                key=lambda x: x[0],
            )
            town = next(
                (x[4] for x in words
                 if re.match(r"^[A-Z][a-z]", x[4]) and 8 < x[1] - y < 20 and x[0] < 120),
                None,
            )
            claims.append({
                "card_code": code,
                "town": town,
                "values": [int(v[4]) for v in values],
            })
    return claims


def extract_punchables(doc):
    """Employees / Events / Post Cards '(with punching)' lists."""
    sections = {"Employees": [], "Events": [], "Post Cards": []}
    current = None
    for pno in range(len(doc)):
        text = doc[pno].get_text()
        if "(with punching)" not in text:
            continue
        for ws in page_lines(doc[pno]):
            joined = " ".join(w[4] for w in ws)
            for name in sections:
                if joined.startswith(f"{name} (with punching)"):
                    current = name
            if current is None:
                continue
            tokens = [w[4] for w in ws]
            code = next((t for t in tokens if re.match(r"^(PC-\d+|\d{4}-\d{2}|[A-Z]{2}-\d{2})$", t)), None)
            if code is None:
                continue
            boxes = [t for t in tokens if set(t) == {"☐"}]
            if len(boxes) < 2:
                continue
            capacity = len(boxes[-1])
            title = " ".join(
                t for t in tokens
                if set(t) != {"☐"} and t != code and not re.match(r"^\d+$", t)
            )
            sections[current].append({"card_code": code, "title": title, "punch_capacity": capacity})
    return sections


def main():
    doc = fitz.open(PDF)
    ref = {
        "tickets": extract_tickets(doc),
        "claims": extract_claims(doc),
        **{k.lower().replace(" ", "_"): v for k, v in extract_punchables(doc).items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"tickets: {len(ref['tickets'])}")
    print(f"claims: {len(ref['claims'])}")
    print(f"employees: {len(ref['employees'])}")
    print(f"events: {len(ref['events'])}")
    print(f"post_cards: {len(ref['post_cards'])}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
