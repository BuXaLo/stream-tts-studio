"""Pure DonationAlerts payload normalization helpers."""
import json
import math


def parse_donation(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), None)
    if not isinstance(payload, dict):
        return None

    donor = payload.get("username") or payload.get("user") or payload.get("donor") or "Добрый человек"
    raw_amount = payload.get("amount", payload.get("sum", 0))
    try:
        amount = float(str(raw_amount).strip().replace(",", "."))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(amount) or amount < 0:
        return None

    currency = payload.get("currency") or "RUB"
    message = payload.get("message") or payload.get("comment") or ""
    return {
        "donor": str(donor),
        "amount": amount,
        "currency": str(currency),
        "message": str(message)
    }
