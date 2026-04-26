import os
import re
from pathlib import Path

from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()

_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


def _normalise_number(number: str) -> str:
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r"[\s\-()]", "", number)
    # Ensure starts with whatsapp:+digits
    if not cleaned.startswith("whatsapp:"):
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        cleaned = "whatsapp:" + cleaned
    return cleaned


def send_text(to: str, message: str) -> dict:
    client = Client(_ACCOUNT_SID, _AUTH_TOKEN)
    to_normalised = _normalise_number(to)
    try:
        msg = client.messages.create(
            from_=_FROM,
            to=to_normalised,
            body=message,
        )
        return {"sid": msg.sid, "status": msg.status}
    except TwilioRestException as e:
        if "not opted in" in str(e).lower() or "60410" in str(e):
            raise RuntimeError(
                f"This number hasn't opted into the Twilio sandbox. "
                f"Send 'join <keyword>' to +14155238886 from that WhatsApp number first."
            )
        raise RuntimeError(f"Twilio error: {e.msg}")


def send_pdf(to: str, message: str, pdf_bytes: bytes, filename: str, base_url: str) -> dict:
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)

    pdf_path = static_dir / filename
    pdf_path.write_bytes(pdf_bytes)

    pdf_url = f"{base_url}/static/{filename}"
    client = Client(_ACCOUNT_SID, _AUTH_TOKEN)
    to_normalised = _normalise_number(to)

    try:
        msg = client.messages.create(
            from_=_FROM,
            to=to_normalised,
            body=message,
            media_url=[pdf_url],
        )
        return {"sid": msg.sid, "status": msg.status, "pdf_url": pdf_url}
    except TwilioRestException as e:
        if "not opted in" in str(e).lower() or "60410" in str(e):
            raise RuntimeError(
                f"This number hasn't opted into the Twilio sandbox. "
                f"Send 'join <keyword>' to +14155238886 from that WhatsApp number first."
            )
        raise RuntimeError(f"Twilio error: {e.msg}")
