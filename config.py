"""Configuration loader — reads from local.settings.json then env vars."""
import os
import json


def _load_local_settings() -> dict:
    """Load Values from local.settings.json if it exists."""
    try:
        path = os.path.join(os.path.dirname(__file__), "local.settings.json")
        with open(path) as f:
            return json.load(f).get("Values", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


_local = _load_local_settings()


def get_config(key: str, default: str | None = None) -> str | None:
    """Get a config value from local settings or environment."""
    return _local.get(key) or os.getenv(key) or default


# PostgreSQL
PG_HOST = get_config("PG_HOST")
PG_PORT = get_config("PG_PORT", "5432")
PG_DATABASE = get_config("PG_DATABASE", "nhutin")
PG_USER = get_config("PG_USER")
PG_PASSWORD = get_config("PG_PASSWORD")
PG_SSLMODE = get_config("PG_SSLMODE", "require")

# Alerts
LOW_BALANCE_THRESHOLD = int(get_config("LOW_BALANCE_THRESHOLD", "500000"))
CONTRACT_ALERT_THRESHOLD = int(get_config("CONTRACT_ALERT_THRESHOLD", "90"))
ALERT_RECIPIENTS = get_config("ALERT_RECIPIENTS", "")  # comma-separated emails

# Gmail SMTP (app password)
GMAIL_ADDRESS = get_config("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = get_config("GMAIL_APP_PASSWORD", "")


def main():
    """Verify config loads correctly."""
    print(f"PG_HOST: {PG_HOST}")
    print(f"PG_PORT: {PG_PORT}")
    print(f"PG_DATABASE: {PG_DATABASE}")
    print(f"PG_USER: {PG_USER}")
    print(f"PG_SSLMODE: {PG_SSLMODE}")
    print(f"PG_PASSWORD: {'***' if PG_PASSWORD else 'NOT SET'}")
    print(f"LOW_BALANCE_THRESHOLD: {LOW_BALANCE_THRESHOLD}")
    print(f"ALERT_RECIPIENTS: {ALERT_RECIPIENTS or 'NOT SET'}")
    print(f"GMAIL_ADDRESS: {GMAIL_ADDRESS or 'NOT SET'}")
    print(f"GMAIL_APP_PASSWORD: {'***' if GMAIL_APP_PASSWORD else 'NOT SET'}")


if __name__ == "__main__":
    main()
