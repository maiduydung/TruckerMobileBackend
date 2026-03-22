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


# Cosmos DB
COSMOS_ENDPOINT = get_config("COSMOS_ENDPOINT")
COSMOS_KEY = get_config("COSMOS_KEY")
COSMOS_DATABASE = get_config("COSMOS_DATABASE", "NhuTinTrucker")
COSMOS_CONTAINER_TRIPS = get_config("COSMOS_CONTAINER_TRIPS", "Trips")
