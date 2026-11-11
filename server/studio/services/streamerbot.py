"""Streamer.bot delivery with bounded retry and failure journaling."""
import json
import logging

import requests


def send_donation_to_streamerbot(
    donor, amount, currency, message, *, load_da_config, journal_failed,
    post=None, logger=None
):
    log = logger or logging.getLogger(__name__)
    post = post or requests.post
    result = {"success": False, "status_code": None, "error": "", "attempts": 0}
    try:
        da_cfg = load_da_config()
        sb_url = da_cfg.get("streamerbot_url", "http://127.0.0.1:7474/DoAction")
        sb_action = da_cfg.get("streamerbot_action", "Donation").strip()
        action = {"name": sb_action} if not sb_action.startswith("{") else json.loads(sb_action)
        if not isinstance(action, dict):
            raise ValueError("Streamer.bot action должен быть объектом")
        payload = {
            "action": action,
            "args": {
                "user": str(donor), "donorName": str(donor),
                "amount": float(amount), "currency": str(currency),
                "message": str(message), "rawInput": str(message)
            }
        }
        for attempt in range(2):
            result["attempts"] += 1
            try:
                response = post(sb_url, json=payload, timeout=(3, 4))
            except requests.exceptions.Timeout as exc:
                result["error"] = "Таймаут Streamer.bot: {}".format(exc)
                break
            except requests.exceptions.ConnectionError as exc:
                result["error"] = "Ошибка соединения со Streamer.bot: {}".format(exc)
                if attempt == 0:
                    continue
                break
            result["status_code"] = response.status_code
            if 200 <= response.status_code < 300:
                log.info("Donation sent to Streamer.bot: %s, HTTP %s, attempts=%s", donor, response.status_code, result["attempts"])
                result["success"] = True
                return result
            body = (response.text or "")[:300]
            result["error"] = "HTTP {}: {}".format(response.status_code, body)
            log.error("Streamer.bot rejected donation: HTTP %s; body=%s", response.status_code, body)
            if 500 <= response.status_code <= 599 and attempt == 0:
                continue
            break
    except Exception as exc:
        result["error"] = str(exc)
        log.exception("Failed to prepare/send donation to Streamer.bot")
    try:
        journal_failed(donor, amount, currency, message, result["error"], result["status_code"], result["attempts"])
    except Exception:
        log.exception("Не удалось записать журнал неотправленного доната")
    return result
