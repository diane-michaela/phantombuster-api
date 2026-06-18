"""
build_autoconnect_segment.py  —  build an Auto Connect CSV from a ranked profiles CSV

Usage:
    python build_autoconnect_segment.py --input ranked_profiles.csv --wave 2
    python build_autoconnect_segment.py --input ranked_profiles.csv --wave all  # merge multiple CSVs

Filters:
  - Country: France only (detected from location field)
  - Connection degree: 2nd only (1st = already connected, 3rd = can't reach)
  - Ranks included: 1–8, 11 (all), 9 (GTM Engineer / Growth Engineer only)
  - Excluded: rank 10 (Sales), 12 (Other/HR), 13 (VC/Investor), rank 9 BizDev/Partnerships
  - Excluded: profiles where autoconnect_sent = True in Airtable (already contacted)

Output:
  - autoconnect_segment_wave{N}.csv — sorted by seniority B first, then rank ascending
  - Column: profileUrl (ready to feed into LinkedIn Auto Connect phantom)
  - Also includes name, linkedinJobTitle, rank, seniority_tag, connectionDegree for reference

After running the Auto Connect phantom, mark sent profiles in Airtable:
  - Check the autoconnect_sent box for all profiles in the segment
  - Future runs of this script will exclude them automatically
"""

import argparse, csv, os, sys, time
import requests

# ── Country detection (FR only) ──────────────────────────────────────────────
CITY_COUNTRY = {
    "paris": "FR", "nantes": "FR", "bordeaux": "FR", "lyon": "FR",
    "marseille": "FR", "toulouse": "FR", "montpellier": "FR", "rennes": "FR",
    "grenoble": "FR", "metz": "FR", "lille": "FR", "nice": "FR",
    "poitiers": "FR", "saint-nazaire": "FR", "lorient": "FR", "mulhouse": "FR",
    "angers": "FR", "strasbourg": "FR", "nancy": "FR", "tours": "FR",
    "rouen": "FR", "reims": "FR", "dijon": "FR", "brest": "FR",
    "le havre": "FR", "clermont-ferrand": "FR", "amiens": "FR", "limoges": "FR",
}

def is_france(location: str) -> bool:
    if not location:
        return False
    lower = location.strip().lower()
    if "france" in lower:
        return True
    last = lower.rsplit(",", 1)[-1].strip()
    if last == "france":
        return True
    for city in CITY_COUNTRY:
        if city in lower:
            return True
    return False


# ── Rank / title filter ──────────────────────────────────────────────────────
INCLUDE_RANKS = {1, 2, 3, 4, 5, 6, 7, 8, 11}

GTM_GROWTH_KEYWORDS = [
    "gtm engineer", "gtm", "growth engineer", "growth hacker",
    "growth product", "growth & marketing engineer",
]

def include_profile(rank_str: str, title: str) -> bool:
    try:
        rank = int(rank_str)
    except (ValueError, TypeError):
        return False

    if rank in INCLUDE_RANKS:
        return True

    if rank == 9:
        title_lower = title.lower()
        return any(kw in title_lower for kw in GTM_GROWTH_KEYWORDS)

    return False


# ── Airtable: fetch already-sent profiles ────────────────────────────────────
PAT   = os.environ.get("AIRTABLE_PAT", "")
BASE  = os.environ.get("AIRTABLE_BASE_ID", "")
TABLE = os.environ.get("AIRTABLE_TABLE_ID", "")

def get_already_sent() -> set:
    """Return set of LinkedIn URLs where autoconnect_sent = true in Airtable."""
    if not PAT:
        print("  (AIRTABLE_PAT not set — skipping already-sent filter)")
        return set()
    headers = {"Authorization": f"Bearer {PAT}"}
    sent = set()
    offset = None
    while True:
        params = {
            "fields[]": ["linkedinProfileUrl", "autoconnect_sent"],
            "filterByFormula": "autoconnect_sent = TRUE()",
            "pageSize": 100,
        }
        if offset:
            params["offset"] = offset
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{TABLE}", headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        for rec in data["records"]:
            url = rec.get("fields", {}).get("linkedinProfileUrl", "").strip()
            if url:
                sent.add(url)
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return sent


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="ranked_profiles.csv")
    parser.add_argument("--wave", default="")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"File not found: {args.input}")

    with open(args.input, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print("Fetching already-sent profiles from Airtable…")
    already_sent = get_already_sent()
    print(f"  {len(already_sent)} profiles already contacted — will exclude")

    kept = []
    stats = {"not_fr": 0, "not_2nd": 0, "rank_excluded": 0, "no_url": 0, "already_sent": 0}

    for row in rows:
        url = row.get("linkedinProfileUrl", "").strip()
        if not url:
            stats["no_url"] += 1
            continue

        if url in already_sent:
            stats["already_sent"] += 1
            continue

        if not is_france(row.get("location", "")):
            stats["not_fr"] += 1
            continue

        if row.get("connectionDegree", "").strip() != "2nd":
            stats["not_2nd"] += 1
            continue

        rank_str = row.get("rank", "").strip()
        title = row.get("linkedinJobTitle", "").strip()

        if not include_profile(rank_str, title):
            stats["rank_excluded"] += 1
            continue

        kept.append({
            "profileUrl":       url,
            "name":             row.get("name", "").strip(),
            "linkedinJobTitle": title,
            "rank":             rank_str,
            "seniority_tag":    row.get("seniority_tag", "").strip(),
            "connectionDegree": row.get("connectionDegree", "").strip(),
            "location":         row.get("location", "").strip(),
        })

    # Sort: seniority B first, then rank ascending
    kept.sort(key=lambda r: (
        0 if r["seniority_tag"] == "B" else 1,
        int(r["rank"]) if r["rank"].isdigit() else 99,
    ))

    wave_suffix = f"_wave{args.wave}" if args.wave else ""
    out_path = f"autoconnect_segment{wave_suffix}.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["profileUrl", "name", "linkedinJobTitle", "rank", "seniority_tag", "connectionDegree", "location"])
        writer.writeheader()
        writer.writerows(kept)

    print(f"\nResults for {args.input}:")
    print(f"  Total input:       {len(rows)}")
    print(f"  Already contacted: {stats['already_sent']}")
    print(f"  Not France:        {stats['not_fr']}")
    print(f"  Not 2nd degree:    {stats['not_2nd']}")
    print(f"  Rank excluded:     {stats['rank_excluded']}")
    print(f"  No LinkedIn URL:   {stats['no_url']}")
    print(f"  ✅ Kept:           {len(kept)}")
    print(f"\nOutput: {out_path}")
    print(f"At 20 connections/day → ~{len(kept) // 20} days to complete")

    # Breakdown by rank
    from collections import Counter
    rank_counts = Counter(r["rank"] for r in kept)
    labels = {
        "1": "AI/ML", "2": "Frontend/Fullstack", "3": "Backend",
        "4": "DevOps/Cloud", "5": "Other Eng", "6": "Product",
        "7": "Design", "8": "Marketing/Growth", "9": "GTM/Growth Eng",
        "11": "Customer Success",
    }
    print("\nBreakdown by rank:")
    for rank in sorted(rank_counts, key=lambda x: int(x) if x.isdigit() else 99):
        label = labels.get(rank, f"Rank {rank}")
        print(f"  {rank:>2} {label:<25} {rank_counts[rank]}")


if __name__ == "__main__":
    main()
