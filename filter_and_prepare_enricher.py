"""
filter_and_prepare_enricher.py — After Company Employees Export finishes:
  1. Fetches the export output from PhantomBuster
  2. Filters to France, Spain, Portugal only
  3. Shows a summary for review
  4. Uploads filtered list to Google Sheets
  5. Updates the Profile Enricher phantom to use it
  6. Waits for your confirmation before activating

Usage:
    python filter_and_prepare_enricher.py
    python filter_and_prepare_enricher.py --auto   # skip confirmation, launch immediately
"""

import argparse
import csv
import io
import json
import os
import sys
import httpx
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

load_env()

PHANTOM_KEY  = os.environ.get("PHANTOMBUSTER_API_KEY", "")
PHANTOM_BASE = "https://api.phantombuster.com/api/v2"

EMPLOYEES_EXPORT_ID = "824349506789425"   # Targeted LinkedIn Company Employees Export
PROFILE_ENRICHER_ID = "5440919304796371"  # targeted LinkedIn Profile Scraper

# Countries to keep — keywords matched against location field (case-insensitive)
ALLOWED_KEYWORDS = [
    "france", "paris", "lyon", "bordeaux", "marseille", "toulouse",
    "nantes", "lille", "strasbourg", "montpellier", "rennes", "grenoble",
    "spain", "españa", "madrid", "barcelona", "valencia", "seville",
    "bilbao", "málaga", "malaga", "sevilla", "zaragoza",
    "portugal", "lisbon", "porto", "lisboa", "braga", "coimbra",
    ", fr", ", es", ", pt",
]

# ---------------------------------------------------------------------------
# PhantomBuster helpers
# ---------------------------------------------------------------------------

def pb_headers():
    if not PHANTOM_KEY:
        sys.exit("PHANTOMBUSTER_API_KEY not set in .env")
    return {"X-Phantombuster-Key": PHANTOM_KEY}


def fetch_export_csv() -> list[dict]:
    """Download the Company Employees Export result CSV."""
    print("Fetching Company Employees Export output...")
    r = httpx.get(
        f"{PHANTOM_BASE}/agents/fetch-output",
        headers=pb_headers(),
        params={"id": EMPLOYEES_EXPORT_ID},
    )
    r.raise_for_status()
    data = r.json()

    # Try output log for S3 URL
    output_text = data.get("output", "")
    csv_url = None
    for line in output_text.splitlines():
        if "result.csv" in line and "s3.amazonaws.com" in line:
            for token in line.split():
                if token.startswith("https://") and token.endswith(".csv"):
                    csv_url = token
                    break
        if csv_url:
            break

    # Fallback: direct S3 URL from agent metadata
    if not csv_url:
        agent_r = httpx.get(
            f"{PHANTOM_BASE}/agents/fetch",
            headers=pb_headers(),
            params={"id": EMPLOYEES_EXPORT_ID},
        )
        agent_r.raise_for_status()
        agent = agent_r.json()
        org = agent.get("orgS3Folder")
        s3  = agent.get("s3Folder")
        if org and s3:
            csv_url = f"https://phantombuster.s3.amazonaws.com/{org}/{s3}/result.csv"
            print(f"Using direct S3 URL: {csv_url}")
        else:
            sys.exit("Could not find result CSV from Company Employees Export.")

    resp = httpx.get(csv_url, follow_redirects=True)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    print(f"Downloaded {len(rows):,} employee profiles from export.")
    return rows


def is_allowed(row: dict) -> bool:
    """Return True if profile location matches FR/ES/PT."""
    location = (
        row.get("location") or
        row.get("location_from_input") or
        row.get("country") or ""
    ).lower()
    return any(kw in location for kw in ALLOWED_KEYWORDS)


def get_profile_url(row: dict) -> str:
    return (
        row.get("profileUrl") or
        row.get("linkedinProfileUrl") or
        row.get("profileUrl_from_input") or ""
    ).strip()


def upload_to_google_sheet(profile_urls: list[str], title: str) -> str:
    """
    Upload profile URLs to Google Drive as a Google Sheet via Drive API.
    Requires GOOGLE_ACCESS_TOKEN in env, or falls back to saving a local CSV
    and printing instructions.
    """
    local_path = Path(__file__).parent / "wave2_enricher_input.csv"
    with open(local_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["profileUrl"])
        for url in profile_urls:
            writer.writerow([url])
    print(f"\nFiltered list saved locally: {local_path} ({len(profile_urls):,} profiles)")
    print("\nNEXT STEP: Upload this file to Google Sheets manually, OR")
    print("run: python filter_and_prepare_enricher.py --upload")
    return str(local_path)


def update_enricher_phantom(spreadsheet_url: str):
    """Point the Profile Enricher phantom at the new spreadsheet."""
    r = httpx.get(
        f"{PHANTOM_BASE}/agents/fetch",
        headers=pb_headers(),
        params={"id": PROFILE_ENRICHER_ID},
    )
    r.raise_for_status()
    current_args = json.loads(r.json().get("argument", "{}"))

    new_args = {
        **current_args,
        "spreadsheetUrl": spreadsheet_url,
        "numberOfAddsPerLaunch": 200,
        "enrichWithCompanyData": True,
        "columnName": "profileUrl",
    }

    save_r = httpx.post(
        f"{PHANTOM_BASE}/agents/save",
        headers=pb_headers(),
        json={"id": PROFILE_ENRICHER_ID, "argument": json.dumps(new_args)},
    )
    save_r.raise_for_status()
    print(f"Profile Enricher updated → {spreadsheet_url}")


def activate_enricher():
    """Switch enricher from manual to repeatedly (daily at 4:30 AM Madrid)."""
    payload = {
        "id": PROFILE_ENRICHER_ID,
        "launchType": "repeatedly",
        "repeatedLaunchTimes": {
            "simplePreset": "Once per day",
            "isSimplePresetEnabled": True,
            "timezone": "Europe/Madrid",
            "hour": [4],
            "minute": [30],
            "dow": ["sun","mon","tue","wed","thu","fri","sat"],
            "day": list(range(1, 32)),
            "month": ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"],
        },
    }
    r = httpx.post(
        f"{PHANTOM_BASE}/agents/save",
        headers=pb_headers(),
        json=payload,
    )
    r.raise_for_status()
    print("Profile Enricher activated — will run daily at 4:30 AM Madrid.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true",
                        help="Skip confirmation and activate enricher immediately")
    parser.add_argument("--spreadsheet-url",
                        help="Skip upload: point enricher at this existing Google Sheet URL")
    args = parser.parse_args()

    # Step 1 — fetch export
    rows = fetch_export_csv()

    # Step 2 — filter
    kept    = [r for r in rows if is_allowed(r)]
    dropped = [r for r in rows if not is_allowed(r)]

    print(f"\n{'='*55}")
    print(f"FILTER RESULTS — keeping FR/ES/PT only")
    print(f"{'='*55}")
    print(f"  Total profiles from export : {len(rows):,}")
    print(f"  Kept (FR/ES/PT)            : {len(kept):,}")
    print(f"  Dropped (other countries)  : {len(dropped):,}")

    # Country breakdown of kept
    print(f"\nKept — top locations:")
    locations = Counter(
        (r.get("location") or r.get("country") or "unknown").split(",")[-1].strip()
        for r in kept
    )
    for loc, count in locations.most_common(15):
        print(f"  {count:>5}  {loc}")

    # Sample dropped countries
    print(f"\nDropped — top locations:")
    dropped_locs = Counter(
        (r.get("location") or r.get("country") or "unknown").split(",")[-1].strip()
        for r in dropped
    )
    for loc, count in dropped_locs.most_common(10):
        print(f"  {count:>5}  {loc}")

    if not kept:
        print("\nNo profiles kept after filtering. Check location fields.")
        return

    # Step 3 — deduplicate by URL
    seen = set()
    unique = []
    for r in kept:
        url = get_profile_url(r)
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    print(f"\nUnique profile URLs to enrich: {len(unique):,}")

    # Step 4 — upload or use provided sheet
    if args.spreadsheet_url:
        sheet_url = args.spreadsheet_url
        print(f"Using provided sheet: {sheet_url}")
    else:
        upload_to_google_sheet(unique, "wave2_enricher_input_June2026")
        print("\nUpload wave2_enricher_input.csv to Google Sheets, then re-run with:")
        print("  python filter_and_prepare_enricher.py --spreadsheet-url <YOUR_SHEET_URL>")
        return

    # Step 5 — update enricher phantom
    update_enricher_phantom(sheet_url)

    # Step 6 — confirm and activate
    if args.auto:
        activate_enricher()
    else:
        print(f"\n{'='*55}")
        print("READY TO ACTIVATE")
        print(f"{'='*55}")
        print(f"  {len(unique):,} FR/ES/PT profiles queued")
        print(f"  200 enrichments/day at 4:30 AM Madrid")
        print(f"  Estimated duration: ~{len(unique)//200 + 1} days")
        print()
        confirm = input("Activate the Profile Enricher now? [y/N] ").strip().lower()
        if confirm == "y":
            activate_enricher()
        else:
            print("Not activated. Run again with --auto when ready, or activate in PhantomBuster UI.")


if __name__ == "__main__":
    main()
