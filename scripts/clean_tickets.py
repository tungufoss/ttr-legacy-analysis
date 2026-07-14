"""Join raw claimed-ticket records against the canonical card_id reference
to fix the frontier-label swap (California/Cascadia, Open Range/Great Plains)
found in the original spreadsheet, and attach a canonical card_id to each row.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "tickets.csv"
REF = ROOT / "data" / "reference" / "card_ids.csv"
OUT = ROOT / "data" / "clean" / "tickets_clean.csv"

# The raw ticket data uses accented French spellings for two cities,
# while the reference table (built from the card list) uses unaccented
# English spellings. Normalize so the join can match on city name.
CITY_FIXUPS = {
    "Montréal": "Montreal",
    "Québec": "Quebec",
}


def normalize_city(name):
    return CITY_FIXUPS.get(name, name)


def load_reference():
    with open(REF, encoding="utf-8-sig", newline="") as f:
        ref_rows = list(csv.DictReader(f))
    lookup = {}
    for r in ref_rows:
        key = frozenset([r["from_city"], r["to_city"]]) | {r["value"]}
        lookup[key] = r
    return lookup


def main():
    lookup = load_reference()

    with open(RAW, encoding="utf-8-sig", newline="") as f:
        raw_rows = list(csv.DictReader(f))

    out_rows = []
    unmatched = []
    for row in raw_rows:
        to_city = normalize_city(row["To"])
        from_city = normalize_city(row["From"])
        key = frozenset([to_city, from_city]) | {row["Dollars"]}
        ref = lookup.get(key)
        if ref is None:
            unmatched.append(row)
            out_rows.append({
                "id": row["id"],
                "card_id": "",
                "frontier": row["Box"],
                "frontier_source": "original (unmatched)",
                "from_city": row["From"],
                "to_city": row["To"],
                "value": row["Dollars"],
                "black": row["Black"],
                "red": row["Red"],
                "blue": row["Blue"],
                "green": row["Green"],
                "yellow": row["Yellow"],
                "active": row["Active"],
                "postcard": row["Postcard"],
            })
            continue
        out_rows.append({
            "id": row["id"],
            "card_id": ref["card_id"],
            "frontier": ref["frontier"],
            "frontier_source": "corrected" if ref["frontier"] != row["Box"] else "original (matched)",
            "from_city": row["From"],
            "to_city": row["To"],
            "value": row["Dollars"],
            "black": row["Black"],
            "red": row["Red"],
            "blue": row["Blue"],
            "green": row["Green"],
            "yellow": row["Yellow"],
            "active": row["Active"],
            "postcard": row["Postcard"],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(out_rows[0].keys())
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    corrected = sum(1 for r in out_rows if r["frontier_source"] == "corrected")
    print(f"wrote {len(out_rows)} rows to {OUT}")
    print(f"  {corrected} rows had their frontier label corrected")
    print(f"  {len(unmatched)} rows could not be matched to a reference card")
    if unmatched:
        print("unmatched ids:", [r["id"] for r in unmatched])


if __name__ == "__main__":
    main()
