import httpx
import os
import json
import sys

BASE = "https://api.phantombuster.com/api/v2"


def headers():
    key = os.environ.get("PHANTOMBUSTER_API_KEY")
    if not key:
        sys.exit("Error: PHANTOMBUSTER_API_KEY environment variable not set.")
    return {"X-Phantombuster-Key": key, "Content-Type": "application/json"}


def list_phantoms():
    """Return all agents in the account."""
    r = httpx.get(f"{BASE}/agents/fetch-all", headers=headers())
    return r.json()


def get_phantom(agent_id: str):
    """Fetch metadata for a single agent by ID."""
    r = httpx.get(f"{BASE}/agents/fetch", headers=headers(), params={"id": agent_id})
    return r.json()


def launch_phantom(agent_id: str, args: dict = None):
    """Launch an agent, optionally overriding its argument."""
    body = {"id": agent_id}
    if args:
        body["argument"] = json.dumps(args)
    r = httpx.post(f"{BASE}/agents/launch", headers=headers(), json=body)
    return r.json()


def stop_phantom(agent_id: str):
    """Abort a running agent."""
    r = httpx.post(f"{BASE}/agents/abort", headers=headers(), json={"id": agent_id})
    return r.json()


def fetch_output(agent_id: str):
    """Retrieve the latest result object written by the agent."""
    r = httpx.get(f"{BASE}/agents/fetch-output", headers=headers(), params={"id": agent_id})
    return r.json()


def save_phantom_argument(agent_id: str, args: dict):
    """Persist a new default argument for the agent."""
    r = httpx.post(
        f"{BASE}/agents/save",
        headers=headers(),
        json={"id": agent_id, "argument": json.dumps(args)},
    )
    return r.json()


def get_phantom_status(agent_id: str):
    """Return the current launch status (running / finished / error …)."""
    info = get_phantom(agent_id)
    return {
        "id": agent_id,
        "status": info.get("data", {}).get("launchType"),
        "last_end_message": info.get("data", {}).get("lastEndMessage"),
    }


def delete_phantom_output(agent_id: str):
    """Delete all stored output/results for an agent."""
    r = httpx.post(
        f"{BASE}/agents/delete-output",
        headers=headers(),
        json={"id": agent_id},
    )
    return r.json()
