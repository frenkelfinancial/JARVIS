import json
import os
from datetime import datetime

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")

_DEFAULTS = {
    "commission": {"last_run": None, "last_output": None, "data": {}},
    "video_pipeline": {"last_run": None, "last_output": None, "data": {}},
    "lead_monitor": {"last_run": None, "last_output": None, "data": {}},
    "ecommerce": {"last_run": None, "last_output": None, "data": {}},
    "video_script": {"last_run": None, "last_output": None, "data": {}},
}


def load() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return dict(_DEFAULTS)
    with open(MEMORY_FILE, "r") as f:
        stored = json.load(f)
    memory = dict(_DEFAULTS)
    memory.update(stored)
    return memory


def save(memory: dict) -> None:
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2, default=str)


def update_agent(agent_name: str, output: str, data: dict = None) -> None:
    memory = load()
    memory[agent_name] = {
        "last_run": datetime.now().isoformat(),
        "last_output": output,
        "data": data or {},
    }
    save(memory)


def get_agent(agent_name: str) -> dict:
    return load().get(agent_name, _DEFAULTS.get(agent_name, {}))
