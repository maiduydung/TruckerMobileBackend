"""Database connection and schema management for the trucker API."""
import logging
import time
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
        t0 = time.time()
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            sslmode=PG_SSLMODE,
        )
        ms = int((time.time() - t0) * 1000)
        if ms > 500:
            logger.warning(f"🐘 DB connect — ⚠️ slow connection: {ms}ms")
        return conn

    @classmethod
    def init_db(cls):
        """Create trips table if it doesn't exist."""
        t0 = time.time()
        logger.info("🐘 init_db — running schema check")
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

                        opening_balance INTEGER DEFAULT 0,
                        total_cost INTEGER DEFAULT 0,
                        closing_balance INTEGER DEFAULT 0,

                        notes TEXT DEFAULT '',
                        is_draft BOOLEAN DEFAULT FALSE,
                        submitted_at TIMESTAMPTZ,
                        received_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                # Add new columns if they don't exist (safe for existing tables)
                for col in ["opening_balance", "total_cost", "closing_balance"]:
                    cur.execute(f"""
                        ALTER TABLE trips ADD COLUMN IF NOT EXISTS {col} INTEGER DEFAULT 0;
                    """)

                # Multi-stop trips: unified stops JSONB array
                cur.execute("""
                    ALTER TABLE trips ADD COLUMN IF NOT EXISTS stops JSONB DEFAULT '[]';
                """)

                # Backfill: migrate old scalar pickup/delivery into stops array
                cur.execute("""
                    UPDATE trips
                    SET stops = jsonb_build_array(
                        jsonb_build_object(
                            'seq', 1, 'type', 'pickup',
                            'location', COALESCE(pickup_location, ''),
                            'date', pickup_date,
                            'weightKg', COALESCE(pickup_weight_kg, 0),
                            'gps', pickup_gps
                        ),
                        jsonb_build_object(
                            'seq', 2, 'type', 'delivery',
                            'location', COALESCE(delivery_location, ''),
                            'date', delivery_date,
                            'weightKg', COALESCE(delivery_weight_kg, 0),
                            'gps', delivery_gps
                        )
                    )
                    WHERE (stops IS NULL OR stops = '[]'::jsonb)
                      AND (pickup_location IS NOT NULL OR delivery_location IS NOT NULL);
                """)
            conn.commit()
        ms = int((time.time() - t0) * 1000)
        logger.info(f"🐘 init_db — ✅ schema verified | {ms}ms")

    @classmethod
    def query(cls, sql: str, params: list | None = None) -> list[dict]:
        """Execute a SELECT query and return rows as dicts."""
        t0 = time.time()
        try:
            with cls.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, params or [])
                    rows = cur.fetchall()
            ms = int((time.time() - t0) * 1000)
            if ms > 1000:
                logger.warning(f"🐘 query — ⚠️ slow query ({ms}ms): {sql[:80]}...")
            return rows
        except Exception:
            logger.error(f"🐘 query — 💥 CRASH\n  SQL: {sql[:120]}\n  Params: {params}\n{traceback.format_exc()}")
            raise

    @classmethod
    def execute(cls, sql: str, params: list | None = None) -> None:
        """Execute a write query (INSERT, UPDATE, DELETE)."""
        t0 = time.time()
        try:
            with cls.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params or [])
                conn.commit()
            ms = int((time.time() - t0) * 1000)
            if ms > 1000:
                logger.warning(f"🐘 execute — ⚠️ slow write ({ms}ms): {sql[:80]}...")
        except Exception:
            logger.error(f"🐘 execute — 💥 CRASH\n  SQL: {sql[:120]}\n  Params: {str(params)[:200]}\n{traceback.format_exc()}")
            raise

    @classmethod
    def fetch_one(cls, sql: str, params: list | None = None) -> dict | None:
        """Execute a SELECT query and return the first row."""
        t0 = time.time()
        try:
            with cls.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, params or [])
                    return cur.fetchone()
        except Exception:
            logger.error(f"🐘 fetch_one — 💥 CRASH\n  SQL: {sql[:120]}\n  Params: {params}\n{traceback.format_exc()}")
            raise


def cold_start():
    """Run on cold start — init DB schema."""
    try:
        Database.init_db()
    except Exception:
        logger.warning(f"🐘 cold_start — ⚠️ DB init skipped (will retry on first request)\n{traceback.format_exc()}")


def main():
    """Test database connectivity."""
    Database.init_db()
    rows = Database.query("SELECT COUNT(*) as cnt FROM trips")
    print(f"Connected OK — {rows[0]['cnt']} trips in DB")


if __name__ == "__main__":
    main()
