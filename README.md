# PhantomBuster API + LinkedIn Profile Ranker

A Python toolkit that connects PhantomBuster to Claude (Anthropic) to control LinkedIn automation agents in plain English and classify scraped profiles by role and seniority — all from your terminal.

---

## Sourcing pipeline

```
LinkedIn Company Employees Export (PB, daily 04:45)
  ↓
filter_and_prepare_enricher.py  ← keeps FR/ES/PT only (~45% of profiles)
  ↓
LinkedIn Profile Scraper (PB, 200/day)  ← enriches filtered profiles
  ↓
rank_profiles.py  ← Claude Haiku Batch API, role rank 1–13
  ↓
ranked_profiles.csv  ← review & shortlist
  ↓
Gem (gem.com) — bulk CSV import of LinkedIn URLs → personal emails
```

**Wave status:**

| Wave | Companies | Status |
|---|---|---|
| Wave 1 (`target_companies_wave1.csv`) | 28 — sales automation FR/ES/PT | Done — 179 ranked profiles |
| Wave 2 (`target_companies_wave2.csv`) | 45 — broader B2B SaaS | Finishing Jun 16, enrichment next |
| Wave 3 (`target_companies_wave3.csv`) | 30 — Bordeaux tech + AI | Prepared — not started yet |

---

## What it does

### 1. PhantomBuster API wrapper (`phantombuster_api.py`)
Eight ready-to-use functions to control any PhantomBuster agent without touching the UI:

| Function | What it does |
|---|---|
| `list_phantoms()` | List all agents in your account |
| `get_phantom(agent_id)` | Fetch metadata for one agent |
| `launch_phantom(agent_id, args=None)` | Launch an agent (optionally override its argument) |
| `stop_phantom(agent_id)` | Abort a running agent |
| `fetch_output(agent_id)` | Get the latest result object from an agent |
| `save_phantom_argument(agent_id, args)` | Persist a new default argument for an agent |
| `get_phantom_status(agent_id)` | Return current launch status + last end message |
| `delete_phantom_output(agent_id)` | Delete all stored output for an agent |

### 2. LinkedIn Profile Ranker (`rank_profiles.py`)
After a PhantomBuster LinkedIn scrape completes, this script:
- Fetches the result CSV automatically from PhantomBuster
- Sends every profile to **Claude Haiku via the Batch API** (async, 50% cheaper than standard)
- Classifies each person into a **role rank (1–13)** and a **seniority tag (B = founder/leader)**
- Outputs `ranked_profiles.csv` with all original columns + `rank` + `seniority_tag`

**Estimated cost: ~$0.17 for 2,000 profiles** (Claude Haiku 4.5 batch pricing).

---

## Role rank reference

| Rank | Role |
|---|---|
| 1 | AI / ML / Data Science / LLM / NLP |
| 2 | Frontend / Mobile / Fullstack |
| 3 | Backend |
| 4 | DevOps / SRE / Infrastructure / Cloud |
| 5 | Other Engineering (QA, Security, Embedded…) |
| 6 | Product |
| 7 | Design |
| 8 | Marketing |
| 9 | Revenue / BizDev / Partnerships |
| 10 | Sales / AE / BDR / SDR |
| 11 | Customer Success |
| 12 | Other / HR / Finance / Unknown |
| 13 | Investor / VC / Advisor |

**Seniority tag B** = Founder, C-suite, VP, Director, Head of, Engineering Manager, and equivalents.

---

## Setup

### Prerequisites
- Python 3.12
- [uv](https://github.com/astral-sh/uv) (fast package manager)
- A [PhantomBuster](https://phantombuster.com) account + API key
- An [Anthropic](https://console.anthropic.com) API key (for the ranker only)

### Install

```bash
git clone https://github.com/diane-michaela/phantombuster-api.git
cd phantombuster-api

# Create venv + install dependencies
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root (never committed — already in `.gitignore`):

```
PHANTOMBUSTER_API_KEY=your_phantombuster_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

---

## Usage

### Control PhantomBuster agents

```python
source .env && python -c "
import phantombuster_api as pb
import json

# List all your agents
agents = pb.list_phantoms()
for a in agents:
    print(a['id'], a['name'])
"
```

Or use it interactively with Claude Code — just open this folder in Claude Code and ask in plain English:

> "List all my phantoms and tell me which ones ran recently"
> "Launch the agent with ID 12345 with this new search URL"
> "What's the status of my targeted companies scraper?"

### Rank scraped profiles

```bash
# Fetch PhantomBuster output and classify all profiles:
source .env && python rank_profiles.py --phantom-id YOUR_AGENT_ID

# Classify a local CSV you already have:
source .env && python rank_profiles.py --input result.csv

# Resume an interrupted batch:
source .env && python rank_profiles.py --batch-id YOUR_BATCH_ID
```

Output: `ranked_profiles.csv` — all original columns plus:
- `rank` — integer 1–13
- `seniority_tag` — `B` for founders/leaders, empty for ICs

---

## Project structure

```
phantombuster-api/
├── phantombuster_api.py              # PhantomBuster API wrapper (8 functions)
├── rank_profiles.py                  # LinkedIn profile classifier (Claude Batch API)
├── filter_and_prepare_enricher.py    # Filter FR/ES/PT → prep enricher input
├── target_companies_wave1.csv        # Wave 1 companies (28, done)
├── target_companies_wave2.csv        # Wave 2 companies (45, in progress)
├── target_companies_wave3.csv        # Wave 3 companies (30, prepared)
├── requirements.txt                  # httpx, anthropic
├── CLAUDE.md                         # Instructions for Claude Code
├── .env                              # API keys — NOT committed
└── .gitignore                        # Excludes .env, .venv, __pycache__
```

---

## Security

- API keys live in `.env` which is excluded from git via `.gitignore`
- Keys are never hard-coded or logged
- The ranker script reads keys from environment variables only

---

## Requirements

- `httpx` — HTTP client for PhantomBuster API calls
- `anthropic` — Claude SDK for profile classification

---

## API notes

Most PhantomBuster endpoints are on **v1**: `https://api.phantombuster.com/api/v1`
The launch endpoint is the exception: `POST https://api.phantombuster.com/api/v2/agents/launch`

Auth header on all calls: `X-Phantombuster-Key: <key>`
