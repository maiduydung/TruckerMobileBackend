"""Database connection and schema management for the trucker API."""
import logging
import traceback

import psycopg2
from psycopg2.extras import RealDictCursor

from config import PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD, PG_SSLMODE

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL connection and schema management."""

    @staticmethod
    def get_conn():
        """Create a new database connection."""
        return psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            sslmode=PG_SSLMODE,
        )

    @classmethod
    def init_db(cls):
        """Create trips table if it doesn't exist."""
        with cls.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trips (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        driver_name TEXT NOT NULL,
                        advance_payment INTEGER DEFAULT 0,

                        pickup_date TIMESTAMPTZ,
                        pickup_location TEXT,
                        pickup_weight_kg INTEGER DEFAULT 0,
                        pickup_gps JSONB,

                        delivery_date TIMESTAMPTZ,
                        delivery_location TEXT,
                        delivery_weight_kg INTEGER DEFAULT 0,
                        delivery_gps JSONB,

                        fuel_nam_phat_vnd INTEGER DEFAULT 0,
                        fuel_hn_liters INTEGER DEFAULT 0,
                        loading_fee_vnd INTEGER DEFAULT 0,
                        additional_costs JSONB DEFAULT '[]',

                        notes TEXT DEFAULT '',
                        is_draft BOOLEAN DEFAULT FALSE,
                        submitted_at TIMESTAMPTZ,
                        received_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
            conn.commit()
        logger.info("DB schema verified")

    @classmethod
    def query(cls, sql: str, params: list | None = None) -> list[dict]:
        """Execute a SELECT query and return rows as dicts."""
        with cls.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or [])
                return cur.fetchall()

    @classmethod
    def execute(cls, sql: str, params: list | None = None) -> None:
        """Execute a write query (INSERT, UPDATE, DELETE)."""
        with cls.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or [])
            conn.commit()

    @classmethod
    def fetch_one(cls, sql: str, params: list | None = None) -> dict | None:
        """Execute a SELECT query and return the first row."""
        with cls.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or [])
                return cur.fetchone()


def cold_start():
    """Run on cold start — init DB schema."""
    try:
        Database.init_db()
    except Exception:
        logger.warning(f"DB init skipped (will retry on first request): {traceback.format_exc()}")


def main():
    """Test database connectivity."""
    Database.init_db()
    rows = Database.query("SELECT COUNT(*) as cnt FROM trips")
    print(f"Connected OK — {rows[0]['cnt']} trips in DB")


if __name__ == "__main__":
    main()
