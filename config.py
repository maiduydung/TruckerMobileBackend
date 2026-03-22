import os
import json

# Load from local.settings.json first, then env vars
try:
    with open(os.path.join(os.path.dirname(__file__), 'local.settings.json')) as f:
        settings = json.load(f)
        local_settings = settings.get('Values', {})
except (FileNotFoundError, json.JSONDecodeError):
    local_settings = {}


def get_config(key, default=None):
    return local_settings.get(key) or os.getenv(key) or default


# PostgreSQL
PG_HOST = get_config("PG_HOST")
PG_PORT = get_config("PG_PORT", "5432")
PG_DATABASE = get_config("PG_DATABASE", "nhutin")
PG_USER = get_config("PG_USER")
PG_PASSWORD = get_config("PG_PASSWORD")
PG_SSLMODE = get_config("PG_SSLMODE", "require")
