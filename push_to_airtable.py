"""
push_to_airtable.py  —  push a ranked_profiles CSV into Airtable
Usage:
    python push_to_airtable.py --input ranked_profiles.csv [--wave 2]

Reads a ranked CSV produced by rank_profiles.py, adds a 'country' column
derived from the location field, creates any missing Airtable fields, then
upserts all records in batches of 10 (Airtable API limit per request).

Target: base app5BF5NrOgR0kZIB / table tbl01XKJ9ZQuADIcn
Requires AIRTABLE_PAT in .env
"""

import argparse, csv, os, sys, time
import requests
from dotenv import load_dotenv

load_dotenv()

PAT   = os.environ.get("AIRTABLE_PAT", "")
BASE  = "app5BF5NrOgR0kZIB"
TABLE = "tbl01XKJ9ZQuADIcn"

if not PAT:
    sys.exit("AIRTABLE_PAT not set — add it to your .env file")

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
    "linkedinCompanySlug", "connectionDegree", "createdBy", "updatedBy",
}

ROLE_LABELS = {
    "1":  "AI / ML / Data Science / LLM / NLP",
    "2":  "Frontend / Mobile / Fullstack",
    "3":  "Backend",
    "4":  "DevOps / SRE / Infrastructure / Cloud",
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

METRO_HINTS = {
    "coimbra metropolitan area": "PT",
    "greater barcelona metropolitan area": "SP",
    "greater alicante area": "SP",
    "greater almería metropolitan area": "SP",
    "greater angers area": "FR",
    "greater nantes metropolitan area": "FR",
    "greater paris metropolitan area": "FR",
    "greater lyon area": "FR",
    "greater bordeaux metropolitan area": "FR",
    "greater madrid metropolitan area": "SP",
    "greater seville metropolitan area": "SP",
    "greater valencia metropolitan area": "SP",
    "greater porto metropolitan area": "PT",
    "greater lisbon metropolitan area": "PT",
    "lisbon metropolitan area": "PT",
    "porto metropolitan area": "PT",
}
COUNTRY_LAST = {"france": "FR", "spain": "SP", "portugal": "PT"}

def detect_country(location: str) -> str:
    if not location:
        return ""
    lower = location.strip().lower()
    for hint, code in METRO_HINTS.items():
        if hint in lower:
            return code
    last = lower.rsplit(",", 1)[-1].strip()
    return COUNTRY_LAST.get(last, "")


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
    }
    for fname, ftype in needed.items():
        if fname not in existing:
            print(f"  Creating field: {fname} ({ftype})")
            create_field(fname, ftype)
            time.sleep(0.3)

    print(f"Pushing {len(rows)} records…")
    total_ok = 0
    batch = []

    for i, row in enumerate(rows):
        record = {}

        for csv_col, value in row.items():
            if not value or not value.strip():
                continue
            at_col = RENAME.get(csv_col, csv_col)
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
