# PhantomBuster API — Claude Code project

## Interpreter
`~/phantombuster-api/.venv/bin/python`

## Environment variable
`PHANTOMBUSTER_API_KEY` — ask me when you need it; never hard-code it.

## How to run a one-off call
```bash
# Key is stored in .env — load it automatically:
source ~/phantombuster-api/.env && ~/phantombuster-api/.venv/bin/python -c "
import phantombuster_api as pb
print(pb.list_phantoms())
"
```

## Available functions in `phantombuster_api.py`

| Function | What it does |
|---|---|
| `list_phantoms()` | List all agents in the account |
| `get_phantom(agent_id)` | Fetch metadata for one agent |
| `launch_phantom(agent_id, args=None)` | Launch an agent (optionally override its argument) |
| `stop_phantom(agent_id)` | Abort a running agent |
| `fetch_output(agent_id)` | Get the latest result object from an agent |
| `save_phantom_argument(agent_id, args)` | Persist a new default argument for an agent |
| `get_phantom_status(agent_id)` | Return current launch status + last end message |
| `delete_phantom_output(agent_id)` | Delete all stored output for an agent |

## Profile ranking (run after PhantomBuster finishes)

```bash
# Fetch PhantomBuster output + classify all profiles in one go:
source ~/phantombuster-api/.env && \
  ~/phantombuster-api/.venv/bin/python rank_profiles.py --phantom-id 3489889683570426

# Or classify a local CSV you already have:
source ~/phantombuster-api/.env && \
  ~/phantombuster-api/.venv/bin/python rank_profiles.py --input pb_result.csv

# If the script was interrupted, resume with the saved batch ID:
source ~/phantombuster-api/.env && \
  ~/phantombuster-api/.venv/bin/python rank_profiles.py --batch-id <batch_id>
```

Output: `ranked_profiles.csv` — all original columns + `rank` (1–13) + `seniority_tag` (B or empty)

Requires `ANTHROPIC_API_KEY` in `.env` in addition to `PHANTOMBUSTER_API_KEY`.

---

## API base
`https://api.phantombuster.com/api/v2`
Auth header: `X-Phantombuster-Key: <key>`
