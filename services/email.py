"""Gmail SMTP email sender using app passwords."""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_RECIPIENTS

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


class EmailSender:
    """Sends emails via Gmail SMTP with app password authentication."""

    @staticmethod
    def _get_recipients() -> list[str]:
        """Parse comma-separated recipient list from config."""
        if not ALERT_RECIPIENTS:
            return []
        return [r.strip() for r in ALERT_RECIPIENTS.split(",") if r.strip()]

    @staticmethod
    def _is_configured() -> bool:
        """Check if email credentials are set."""
        return bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD and ALERT_RECIPIENTS)

    @classmethod
    def send(cls, subject: str, html_body: str) -> bool:
        """Send an HTML email to all configured recipients.

        Returns True if sent successfully, False otherwise.
        """
        if not cls._is_configured():
            logger.warning("📧 email — ⚠️ not configured (missing GMAIL_ADDRESS, "
                           "GMAIL_APP_PASSWORD, or ALERT_RECIPIENTS)")
            return False

        recipients = cls._get_recipients()
        if not recipients:
            logger.warning("📧 email — ⚠️ no recipients configured")
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
                server.sendmail(GMAIL_ADDRESS, recipients, msg.as_string())
            logger.info(f"📧 email — ✅ sent to {recipients}")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("📧 email — ❌ authentication failed (check app password)")
            return False
        except Exception as e:
            logger.error(f"📧 email — ❌ send failed: {e}")
            return False


def main():
    """Test email configuration and send a test message."""
    if not EmailSender._is_configured():
        print("Email not configured — set GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_RECIPIENTS")
        return
    sent = EmailSender.send(
        subject="[Test] Pathfinder Trucker Alert",
        html_body="<p>This is a test email from the Pathfinder Trucker API.</p>",
    )
    print(f"Test email {'sent' if sent else 'failed'}")


if __name__ == "__main__":
    main()
