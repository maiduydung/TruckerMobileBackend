"""Balance alert endpoints — checks trucker closing balances and sends email alerts."""
import logging
import time
import traceback

import azure.functions as func

from config import LOW_BALANCE_THRESHOLD, CONTRACT_ALERT_THRESHOLD
from services.database import Database
from services.email import EmailSender
from services.response import ResponseHelper

logger = logging.getLogger(__name__)


class AlertFunctions:
    """Registers alert-related HTTP endpoints."""

    @staticmethod
    def register(app: func.FunctionApp):
        """Bind alert routes to the function app."""

        @app.function_name(name="check_balances")
        @app.route(route="alerts/check-balances", methods=["GET"],
                   auth_level=func.AuthLevel.FUNCTION)
        def check_balances(req: func.HttpRequest) -> func.HttpResponse:
            """Check trucker balances and send alert if any are low."""
            return AlertFunctions._check_balances(req)

        @app.function_name(name="check_contracts")
        @app.route(route="alerts/check-contracts", methods=["GET"],
                   auth_level=func.AuthLevel.FUNCTION)
        def check_contracts(req: func.HttpRequest) -> func.HttpResponse:
            """Check contracts nearing completion and send alert."""
            return AlertFunctions._check_contracts(req)

    @staticmethod
    def _get_low_balance_drivers() -> list[dict]:
        """Find drivers whose latest trip has closing_balance below threshold.

        For each driver, picks the most recent completed trip's closing balance.
        """
        rows = Database.query("""
            SELECT DISTINCT ON (driver_name)
                driver_name,
                closing_balance,
                submitted_at
            FROM trips
            WHERE is_draft = FALSE
            ORDER BY driver_name, submitted_at DESC
        """)
        return [
            {
                "driver": r["driver_name"],
                "balance": r["closing_balance"],
                "last_trip": r["submitted_at"],
            }
            for r in rows
            if r["closing_balance"] < LOW_BALANCE_THRESHOLD
        ]

    @staticmethod
    def _build_alert_email(drivers: list[dict]) -> str:
        """Build HTML email body for low-balance alert."""
        def fmt_vnd(amount: int) -> str:
            """Format VND amount with thousand separators."""
            return f"{amount:,}".replace(",", ".")

        rows_html = ""
        for d in drivers:
            color = "#ef4444" if d["balance"] < 0 else "#d97706"
            rows_html += (
                f"<tr>"
                f"<td style='padding:10px 16px;border-bottom:1px solid #e5e7eb;'>"
                f"<strong>{d['driver']}</strong></td>"
                f"<td style='padding:10px 16px;border-bottom:1px solid #e5e7eb;"
                f"text-align:right;color:{color};font-weight:700;'>"
                f"{fmt_vnd(d['balance'])}d</td>"
                f"</tr>"
            )

        return f"""
        <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:500px;margin:0 auto;">
            <div style="background:#1273FF;color:white;padding:20px 24px;border-radius:12px 12px 0 0;">
                <h2 style="margin:0;font-size:18px;">Pathfinder Trucker Alert</h2>
                <p style="margin:6px 0 0;opacity:0.85;font-size:13px;">
                    Can ung them cho tai xe</p>
            </div>
            <div style="background:white;border:1px solid #e5e7eb;border-top:none;
                        border-radius:0 0 12px 12px;overflow:hidden;">
                <table style="width:100%;border-collapse:collapse;font-size:14px;">
                    <thead>
                        <tr style="background:#f9fafb;">
                            <th style="padding:10px 16px;text-align:left;font-size:12px;
                                       color:#6b7280;text-transform:uppercase;">Tai xe</th>
                            <th style="padding:10px 16px;text-align:right;font-size:12px;
                                       color:#6b7280;text-transform:uppercase;">Du cuoi</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
                <div style="padding:16px 16px;background:#fffbeb;border-top:1px solid #fbbf24;
                            font-size:12px;color:#92400e;">
                    Nguong canh bao: {fmt_vnd(LOW_BALANCE_THRESHOLD)}d
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _get_alerting_contracts() -> list[dict]:
        """Find active contracts where completion >= threshold %.

        Uses the same lateral join as the contracts list endpoint.
        """
        import datetime
        rows = Database.query("""
            SELECT c.id, c.name, c.subject, c.target_weight_kg, c.end_date,
                   COALESCE(matched.delivered_kg, 0) AS delivered_kg
            FROM contracts c
            LEFT JOIN LATERAL (
                SELECT SUM(del_weight) AS delivered_kg
                FROM (
                    SELECT DISTINCT t.id,
                        (SELECT COALESCE(SUM((ds->>'weightKg')::int), 0)
                         FROM jsonb_array_elements(t.stops) ds
                         WHERE (ds->>'type') = 'delivery'
                        ) AS del_weight
                    FROM trips t, jsonb_array_elements(t.stops) AS stop
                    WHERE LOWER(TRIM(stop->>'location')) = LOWER(TRIM(c.subject))
                      AND t.submitted_at >= c.start_date
                      AND t.submitted_at <= c.end_date + interval '1 day'
                      AND t.is_draft = FALSE
                ) matched_trips
            ) matched ON true
            WHERE c.status = 'active'
        """)
        now = datetime.date.today()
        alerting = []
        for r in rows:
            target = r["target_weight_kg"]
            delivered = r["delivered_kg"] or 0
            pct = round((delivered / target) * 100, 1) if target > 0 else 0
            if pct >= CONTRACT_ALERT_THRESHOLD:
                days_left = (r["end_date"] - now).days if isinstance(r["end_date"], datetime.date) else 0
                alerting.append({
                    "name": r["name"],
                    "subject": r["subject"],
                    "target_kg": target,
                    "delivered_kg": delivered,
                    "remaining_kg": max(target - delivered, 0),
                    "pct": pct,
                    "days_left": days_left,
                })
        return alerting

    @staticmethod
    def _build_contract_alert_email(contracts: list[dict]) -> str:
        """Build HTML email body for contract completion alert."""
        def fmt(val: int) -> str:
            return f"{val:,}".replace(",", ".")

        td = "padding:10px 16px;border-bottom:1px solid #e5e7eb;"
        th = "padding:10px 16px;font-size:12px;color:#6b7280;text-transform:uppercase;"
        rows_html = ""
        for c in contracts:
            color = "#059669" if c["pct"] >= 100 else "#d97706"
            rows_html += (
                f"<tr><td style='{td}'><strong>{c['name']}</strong><br>"
                f"<span style='font-size:12px;color:#6b7280;'>{c['subject']}</span></td>"
                f"<td style='{td}text-align:right;'>{fmt(c['delivered_kg'])}/{fmt(c['target_kg'])}kg</td>"
                f"<td style='{td}text-align:right;color:{color};font-weight:700;'>{c['pct']}%</td>"
                f"<td style='{td}text-align:right;'>{c['days_left']} ngay</td></tr>"
            )
        return (
            "<div style=\"font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:0 auto;\">"
            "<div style='background:#7c3aed;color:white;padding:20px 24px;border-radius:12px 12px 0 0;'>"
            "<h2 style='margin:0;font-size:18px;'>Pathfinder Contract Alert</h2>"
            "<p style='margin:6px 0 0;opacity:0.85;font-size:13px;'>Hop dong sap hoan thanh</p></div>"
            "<div style='background:white;border:1px solid #e5e7eb;border-top:none;"
            "border-radius:0 0 12px 12px;overflow:hidden;'>"
            f"<table style='width:100%;border-collapse:collapse;font-size:14px;'><thead>"
            f"<tr style='background:#f9fafb;'><th style='{th}text-align:left;'>Hop dong</th>"
            f"<th style='{th}text-align:right;'>Da giao</th>"
            f"<th style='{th}text-align:right;'>Tien do</th>"
            f"<th style='{th}text-align:right;'>Con lai</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
            f"<div style='padding:16px;background:#f5f3ff;border-top:1px solid #c4b5fd;"
            f"font-size:12px;color:#5b21b6;'>Nguong canh bao: {CONTRACT_ALERT_THRESHOLD}% hoan thanh"
            "</div></div></div>"
        )

    @staticmethod
    def _check_contracts(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/alerts/check-contracts."""
        t0 = time.time()
        logger.info(f"🔔 GET /api/alerts/check-contracts — threshold={CONTRACT_ALERT_THRESHOLD}%")
        try:
            contracts = AlertFunctions._get_alerting_contracts()
            ms = int((time.time() - t0) * 1000)

            if not contracts:
                logger.info(f"🔔 check-contracts — ✅ no contracts at threshold | {ms}ms")
                return ResponseHelper.json({
                    "status": "ok",
                    "message": "No contracts at alert threshold",
                    "threshold": CONTRACT_ALERT_THRESHOLD,
                    "alerted": [],
                })

            logger.warning(f"🔔 check-contracts — ⚠️ {len(contracts)} contract(s) at "
                           f">={CONTRACT_ALERT_THRESHOLD}%: "
                           f"{[c['name'] for c in contracts]}")

            email_sent = EmailSender.send(
                subject=f"[Pathfinder] {len(contracts)} hop dong sap hoan thanh",
                html_body=AlertFunctions._build_contract_alert_email(contracts),
            )

            ms = int((time.time() - t0) * 1000)
            logger.info(f"🔔 check-contracts — ✅ done | email={'sent' if email_sent else 'skipped'} "
                        f"| {ms}ms")

            return ResponseHelper.json({
                "status": "alert",
                "threshold": CONTRACT_ALERT_THRESHOLD,
                "alerted": contracts,
                "emailSent": email_sent,
            })

        except Exception:
            logger.error(f"🔔 check-contracts — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _check_balances(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/alerts/check-balances."""
        t0 = time.time()
        logger.info(f"🔔 GET /api/alerts/check-balances — threshold={LOW_BALANCE_THRESHOLD:,}")
        try:
            drivers = AlertFunctions._get_low_balance_drivers()
            ms = int((time.time() - t0) * 1000)

            if not drivers:
                logger.info(f"🔔 check-balances — ✅ all drivers OK | {ms}ms")
                return ResponseHelper.json({
                    "status": "ok",
                    "message": "All drivers above threshold",
                    "threshold": LOW_BALANCE_THRESHOLD,
                    "alerted": [],
                })

            logger.warning(f"🔔 check-balances — ⚠️ {len(drivers)} driver(s) below "
                           f"{LOW_BALANCE_THRESHOLD:,}: "
                           f"{[d['driver'] for d in drivers]}")

            email_sent = EmailSender.send(
                subject=f"[Pathfinder] {len(drivers)} tai xe can ung them",
                html_body=AlertFunctions._build_alert_email(drivers),
            )

            ms = int((time.time() - t0) * 1000)
            logger.info(f"🔔 check-balances — ✅ done | email={'sent' if email_sent else 'skipped'} "
                        f"| {ms}ms")

            return ResponseHelper.json({
                "status": "alert",
                "threshold": LOW_BALANCE_THRESHOLD,
                "alerted": drivers,
                "emailSent": email_sent,
            })

        except Exception:
            logger.error(f"🔔 check-balances — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)


def main():
    """Test balance check locally."""
    drivers = AlertFunctions._get_low_balance_drivers()
    if drivers:
        print(f"Low balance drivers ({LOW_BALANCE_THRESHOLD:,} threshold):")
        for d in drivers:
            print(f"  {d['driver']}: {d['balance']:,}d")
    else:
        print("All drivers above threshold")


if __name__ == "__main__":
    main()
