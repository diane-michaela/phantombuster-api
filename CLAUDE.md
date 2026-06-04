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

## API base
`https://api.phantombuster.com/api/v2`
Auth header: `X-Phantombuster-Key: <key>`
