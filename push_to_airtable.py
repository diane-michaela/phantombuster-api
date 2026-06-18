"""
push_to_airtable.py  —  push a ranked_profiles CSV into Airtable
Usage:
    python push_to_airtable.py --input ranked_profiles.csv [--wave 2]

Reads a ranked CSV produced by rank_profiles.py, adds a 'country' column
derived from the location field, creates any missing Airtable fields, then
upserts all records in batches of 10 (Airtable API limit per request).

Target: base + table read from AIRTABLE_BASE_ID / AIRTABLE_TABLE_ID in .env
Requires AIRTABLE_PAT, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID in .env
"""

import argparse, csv, os, sys, time
import requests
from dotenv import load_dotenv

load_dotenv()

PAT   = os.environ.get("AIRTABLE_PAT", "")
BASE  = os.environ.get("AIRTABLE_BASE_ID", "")
TABLE = os.environ.get("AIRTABLE_TABLE_ID", "")

if not PAT:
    sys.exit("AIRTABLE_PAT not set — add it to your .env file")
if not BASE or not TABLE:
    sys.exit("AIRTABLE_BASE_ID and AIRTABLE_TABLE_ID must be set in your .env file")

HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

# CSV column → Airtable field name
RENAME = {
    "name": "fullName",
}

# Fields that must be int
NUMBER_FIELDS = {"rank", "linkedinConnectionsCount", "linkedinFollowersCount", "linkedinProfileId"}

# Fields that must be bool
BOOLEAN_FIELDS = {"linkedinIsOpenToWorkBadge", "linkedinIsHiringBadge"}

# Locked singleSelect fields created by PhantomBuster — skip them
SKIP_FIELDS = {
    "companyName", "linkedinCompanyUrl", "salesNavigatorCompanyUrl",
    "companyWebsite", "linkedinJobDateRange", "companyIndustry",
    "linkedinSchoolDateRange", "linkedinPreviousSchoolDateRange",
    "linkedinCompanySlug", "createdBy", "updatedBy",
    "linkedinIsOpenToWorkBadge", "linkedinIsHiringBadge",
}

ROLE_LABELS = {
    "1":  "AI / ML / Data Science",
    "2":  "Frontend / Mobile / Fullstack",
    "3":  "Backend",
    "4":  "DevOps / SRE / Infrastructure",
    "5":  "Other Engineering",
    "6":  "Product",
    "7":  "Design",
    "8":  "Marketing / Growth",
    "9":  "Revenue / BizDev / Partnerships",
    "10": "Sales / AE / BDR / SDR",
    "11": "Customer Success / Enablement",
    "12": "Other / HR / Finance / Unknown",
    "13": "Investor / VC / Advisor",
}

# Cities/regions whose name alone implies a country (used for "Greater X" patterns)
CITY_COUNTRY = {
    # France
    "paris": "FR", "nantes": "FR", "bordeaux": "FR", "lyon": "FR",
    "marseille": "FR", "toulouse": "FR", "montpellier": "FR", "rennes": "FR",
    "grenoble": "FR", "metz": "FR", "lille": "FR", "nice": "FR",
    "poitiers": "FR", "saint-nazaire": "FR", "lorient": "FR", "mulhouse": "FR",
    "angers": "FR", "strasbourg": "FR", "nancy": "FR", "tours": "FR",
    "rouen": "FR", "reims": "FR", "dijon": "FR", "brest": "FR",
    "le havre": "FR", "clermont-ferrand": "FR", "amiens": "FR", "limoges": "FR",
    # Spain
    "barcelona": "SP", "madrid": "SP", "valencia": "SP", "seville": "SP",
    "sevilla": "SP", "bilbao": "SP", "murcia": "SP", "zaragoza": "SP",
    "málaga": "SP", "malaga": "SP", "alicante": "SP", "córdoba": "SP",
    "cordoba": "SP", "terrassa": "SP", "tarragona": "SP", "pamplona": "SP",
    "valladolid": "SP", "san sebastián": "SP", "san sebastian": "SP",
    "santiago de compostela": "SP", "donostia": "SP",
    # Portugal
    "lisbon": "PT", "porto": "PT", "braga": "PT", "coimbra": "PT",
    "faro": "PT", "funchal": "PT", "aveiro": "PT", "setúbal": "PT",
    "setubal": "PT", "viseu": "PT", "leiria": "PT", "évora": "PT",
}

def detect_country(location: str) -> str:
    if not location:
        return ""
    lower = location.strip().lower()
    # Country name anywhere in string (handles "Greater Córdoba, Spain Area" etc.)
    if "france" in lower:
        return "FR"
    if "spain" in lower:
        return "SP"
    if "portugal" in lower:
        return "PT"
    # Last segment after final comma ("Barcelona, Catalonia, Spain")
    last = lower.rsplit(",", 1)[-1].strip()
    if last in ("france", "spain", "portugal"):
        return {"france": "FR", "spain": "SP", "portugal": "PT"}[last]
    # City/region name lookup for "Greater X Metropolitan Area/Region" patterns
    for city, code in CITY_COUNTRY.items():
        if city in lower:
            return code
    return ""


def get_existing_fields() -> set:
    r = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{BASE}/tables",
        headers=HEADERS,
    )
    r.raise_for_status()
    for t in r.json()["tables"]:
        if t["id"] == TABLE:
            return {f["name"] for f in t["fields"]}
    return set()

def create_field(name: str, ftype: str = "singleLineText"):
    payload = {"name": name, "type": ftype}
    if ftype == "number":
        payload["options"] = {"precision": 0}
    r = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{BASE}/tables/{TABLE}/fields",
        headers=HEADERS, json=payload,
    )
    if r.status_code not in (200, 422):
        print(f"  WARNING creating field '{name}': {r.status_code} {r.text[:120]}")

def push_batch(records: list) -> int:
    r = requests.post(
        f"https://api.airtable.com/v0/{BASE}/{TABLE}",
        headers=HEADERS,
        json={"records": [{"fields": rec} for rec in records]},
    )
    if r.status_code != 200:
        print(f"\n  ERROR: {r.status_code} {r.text[:200]}")
        return 0
    return len(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to ranked CSV")
    parser.add_argument("--wave", default="", help="Wave label (e.g. 2)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"File not found: {args.input}")

    with open(args.input, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Read {len(rows)} rows from {args.input}")

    print("Checking Airtable fields…")
    existing = get_existing_fields()
    needed = {
        "fullName": "singleLineText",
        "rank": "number",
        "role": "singleLineText",
        "seniority_tag": "singleLineText",
        "country": "singleLineText",
        "wave": "singleLineText",
        "professionalEmail": "email",
        "linkedinConnectionsCount": "number",
        "connectionDegree": "singleLineText",
        "autoconnect_sent": "checkbox",
    }
    for fname, ftype in needed.items():
        if fname not in existing:
            print(f"  Creating field: {fname} ({ftype})")
            create_field(fname, ftype)
            time.sleep(0.3)
    # allowlist: only push fields that exist in Airtable (avoids 422 on unknown fields)
    allowed_fields = existing | set(needed.keys())

    print(f"Pushing {len(rows)} records…")
    total_ok = 0
    batch = []

    for i, row in enumerate(rows):
        record = {}

        for csv_col, value in row.items():
            if not value or not value.strip():
                continue
            at_col = RENAME.get(csv_col, csv_col)
            if at_col not in allowed_fields:
                continue
            if at_col in SKIP_FIELDS:
                continue
            if at_col in NUMBER_FIELDS:
                try:
                    value = int(float(value))
                except (ValueError, TypeError):
                    continue
            elif at_col in BOOLEAN_FIELDS:
                value = value.strip().lower() in ("true", "1", "yes")
            record[at_col] = value

        country = detect_country(row.get("location", ""))
        if country:
            record["country"] = country

        rank_str = str(row.get("rank", "")).strip()
        if rank_str in ROLE_LABELS:
            record["role"] = ROLE_LABELS[rank_str]

        if args.wave:
            record["wave"] = f"Wave {args.wave}"

        batch.append(record)

        if len(batch) == 10:
            total_ok += push_batch(batch)
            batch = []
            time.sleep(0.22)

        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}/{len(rows)} rows processed…")

    if batch:
        total_ok += push_batch(batch)

    print(f"\nDone — {total_ok}/{len(rows)} records pushed to Airtable")


if __name__ == "__main__":
    main()
