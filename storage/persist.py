import json
import os
from storage.memory import memory  # Исправлен импорт

DATA_DIR = "guild_data"
os.makedirs(DATA_DIR, exist_ok=True)

def get_file_path(name, guild_id):
    return os.path.join(DATA_DIR, f"{name}_{guild_id}.json")

def load_presets(guild_id):
    file = get_file_path("presets", guild_id)
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            memory.presets[guild_id] = data.get("presets", [])
            memory.group_leaders[guild_id] = {int(k): v for k, v in data.get("leaders", {}).items()}
    else:
        memory.presets[guild_id] = []
        memory.group_leaders[guild_id] = {}

def save_presets(guild_id):
    file = get_file_path("presets", guild_id)
    data = {
        "presets": memory.presets.get(guild_id, []),
        "leaders": {str(k): v for k, v in memory.group_leaders.get(guild_id, {}).items()}
    }
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_user_roles(guild_id):
    file = get_file_path("user_roles", guild_id)
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            memory.user_roles[guild_id] = {int(k): v for k, v in json.load(f).items()}
    else:
        memory.user_roles[guild_id] = {}

def save_user_roles(guild_id):
    file = get_file_path("user_roles", guild_id)
    data = {str(k): v for k, v in memory.user_roles.get(guild_id, {}).items()}
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_schedules(guild_id):
    file = get_file_path("schedules", guild_id)
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            memory.schedules[guild_id] = json.load(f)
    else:
        memory.schedules[guild_id] = []

def save_schedules(guild_id):
    file = get_file_path("schedules", guild_id)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(memory.schedules.get(guild_id, []), f, ensure_ascii=False, indent=2)