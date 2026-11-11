"""DonationAlerts OAuth/Centrifugo worker and Streamer.bot delivery orchestration."""
import asyncio
import json
import logging
import os
import threading
import time
from typing import Optional

import requests
import websockets

from studio.core.storage import get_file_lock
from studio.services.donations import parse_donation
from studio.services.streamerbot import send_donation_to_streamerbot

DA_AUTH_URL = "https://www.donationalerts.com/oauth/authorize"
DA_TOKEN_URL = "https://www.donationalerts.com/oauth/token"
DA_USER_API_URL = "https://www.donationalerts.com/api/v1/user/oauth"
DA_SUBSCRIBE_API_URL = "https://www.donationalerts.com/api/v1/centrifuge/subscribe"
DA_CENTRIFUGO_WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"
DA_SCOPES = "oauth-donation-subscribe oauth-user-show"
_failed_donations_lock = threading.Lock()

load_config = load_da_config = load_da_tokens = save_da_tokens = None
DA_TOKENS_FILE = LOG_DIR = FAILED_DONATIONS_FILE = ""

def configure_worker(server_dir, log_dir, config_loader, da_config_loader, tokens_loader, tokens_saver):
    global load_config, load_da_config, load_da_tokens, save_da_tokens
    global DA_TOKENS_FILE, LOG_DIR, FAILED_DONATIONS_FILE
    load_config = config_loader
    load_da_config = da_config_loader
    load_da_tokens = tokens_loader
    save_da_tokens = tokens_saver
    DA_TOKENS_FILE = os.path.join(server_dir, "da_tokens.json")
    LOG_DIR = log_dir
    FAILED_DONATIONS_FILE = os.path.join(log_dir, "streamerbot_failed_donations.jsonl")

class DonationAlertsWorker:
    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.is_connected = False
        self.authorized_user = ""
        self.last_error = ""

    def get_redirect_uri(self) -> str:
        cfg = load_config()
        port = cfg.get("port", 8765)
        return f"http://127.0.0.1:{port}/api/da/callback"

    def refresh_tokens(self, refresh_token: str, client_id: str, client_secret: str) -> Optional[dict]:
        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "scope": DA_SCOPES
        }
        try:
            resp = requests.post(DA_TOKEN_URL, data=payload, timeout=10)
            if resp.status_code != 200:
                logging.getLogger(__name__).warning(
                    "DonationAlerts token refresh failed: HTTP %s (%s)",
                    resp.status_code, resp.text[:300]
                )
                return None
            tokens = resp.json()
            with get_file_lock(DA_TOKENS_FILE):
                save_da_tokens(tokens)
            return tokens
        except Exception:
            logging.getLogger(__name__).exception("DonationAlerts token refresh request failed")
            return None

    def get_access_token(self):
        tokens = load_da_tokens()
        da_cfg = load_da_config()
        if not tokens or not da_cfg.get("client_id") or not da_cfg.get("client_secret"):
            self.last_error = "Требуется авторизация OAuth"
            return None

        def fetch_profile(access_token):
            response = requests.get(
                DA_USER_API_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=8
            )
            if response.status_code == 200:
                profile = response.json().get("data")
                if isinstance(profile, dict):
                    return profile
            return response

        try:
            access_token = tokens.get("access_token")
            profile = fetch_profile(access_token)
            if isinstance(profile, requests.Response) and profile.status_code == 401 and tokens.get("refresh_token"):
                refreshed = self.refresh_tokens(
                    tokens["refresh_token"], da_cfg["client_id"], da_cfg["client_secret"]
                )
                if not refreshed:
                    self.last_error = "OAuth-токен DonationAlerts истёк. Требуется повторная авторизация."
                    return None
                access_token = refreshed.get("access_token")
                profile = fetch_profile(access_token)

            if isinstance(profile, requests.Response):
                self.last_error = f"DonationAlerts временно недоступен (HTTP {profile.status_code})."
                return None

            if not profile.get("id") or not profile.get("socket_connection_token"):
                self.last_error = "DonationAlerts вернул неполный профиль пользователя."
                return None

            self.authorized_user = str(profile.get("name") or "")
            return access_token, profile
        except requests.exceptions.RequestException as exc:
            self.last_error = f"DonationAlerts временно недоступен: {exc}"
            return None
        except Exception as exc:
            self.last_error = f"Ошибка ответа DonationAlerts: {exc}"
            return None

    def _journal_failed_donation(self, donor, amount, currency, message, reason, status_code, attempts):
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "donor": str(donor),
            "amount": amount,
            "currency": str(currency),
            "message": str(message),
            "reason": str(reason),
            "status_code": status_code,
            "attempts": attempts
        }
        try:
            with _failed_donations_lock:
                os.makedirs(LOG_DIR, exist_ok=True)
                with open(FAILED_DONATIONS_FILE, "a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logging.getLogger(__name__).exception("Не удалось записать журнал неотправленного доната")

    def send_to_streamerbot(self, donor: str, amount: float, currency: str, message: str):
        return send_donation_to_streamerbot(
            donor, amount, currency, message,
            load_da_config=load_da_config,
            journal_failed=self._journal_failed_donation,
        )

    async def run_loop(self):
        reconnect_delays = (5, 10, 30, 60)
        reconnect_index = 0

        while True:
            da_cfg = await asyncio.to_thread(load_da_config)
            if not da_cfg.get("enabled", False):
                self.is_connected = False
                await asyncio.sleep(1)
                continue

            auth_result = await asyncio.to_thread(self.get_access_token)
            if not auth_result:
                self.is_connected = False
                self.last_error = self.last_error or "DonationAlerts временно недоступен."
                delay = reconnect_delays[reconnect_index]
                reconnect_index = min(reconnect_index + 1, len(reconnect_delays) - 1)
                logging.getLogger(__name__).warning(
                    "DonationAlerts connection unavailable; retry in %ss: %s", delay, self.last_error
                )
                await asyncio.sleep(delay)
                continue

            access_token, profile = auth_result
            try:
                user_id = profile["id"]
                socket_token = profile["socket_connection_token"]
                channel = f"$alerts:donation_{user_id}"

                async with websockets.connect(
                    DA_CENTRIFUGO_WS_URL, ping_interval=20, ping_timeout=10
                ) as ws:
                    await ws.send(json.dumps({"params": {"token": socket_token}, "id": 1}))
                    connect_res = json.loads(await ws.recv())
                    client_id = connect_res.get("result", {}).get("client")
                    if not client_id:
                        raise RuntimeError(f"Ошибка авторизации Centrifugo: {connect_res}")

                    sub_response = await asyncio.to_thread(
                        requests.post,
                        DA_SUBSCRIBE_API_URL,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={"channels": [channel], "client": client_id},
                        timeout=10
                    )
                    sub_response.raise_for_status()
                    sub_data = sub_response.json()
                    sub_token = next(
                        (item.get("token") for item in sub_data.get("channels", [])
                         if item.get("channel") == channel),
                        None
                    )
                    if not sub_token:
                        raise RuntimeError("Не удалось получить токен подписки на канал алертов")

                    await ws.send(json.dumps({
                        "params": {"channel": channel, "token": sub_token},
                        "method": 1,
                        "id": 2
                    }))
                    sub_res = json.loads(await ws.recv())
                    if "error" in sub_res:
                        raise RuntimeError(f"Ошибка подписки: {sub_res['error']}")

                    self.is_connected = True
                    self.last_error = ""
                    reconnect_index = 0
                    logging.getLogger(__name__).info(
                        "Подключено к DA Centrifugo (аккаунт: %s)", self.authorized_user
                    )

                    while True:
                        current_cfg = await asyncio.to_thread(load_da_config)
                        if not current_cfg.get("enabled", False):
                            break

                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        except asyncio.TimeoutError:
                            continue

                        if not raw_msg or not raw_msg.strip():
                            continue

                        for line in raw_msg.strip().split("\n"):
                            line = line.strip()
                            if not line or line == "{}":
                                continue
                            try:
                                data = json.loads(line)
                            except (TypeError, ValueError):
                                logging.getLogger(__name__).warning("Пропущено некорректное JSON-событие DonationAlerts")
                                continue

                            payload_data = None
                            if isinstance(data, dict):
                                result_data = data.get("result", {}).get("data", {})
                                push_data = data.get("push", {}).get("pub", {})
                                if isinstance(result_data, dict):
                                    payload_data = result_data.get("data")
                                if payload_data is None and isinstance(push_data, dict):
                                    payload_data = push_data.get("data")

                            donation = parse_donation(payload_data)
                            if donation is None:
                                if payload_data is not None:
                                    logging.getLogger(__name__).warning(
                                        "Пропущено некорректное событие доната DonationAlerts"
                                    )
                                continue

                            logging.getLogger(__name__).info(
                                "Получен донат: %s, %s %s", donation["donor"],
                                donation["amount"], donation["currency"]
                            )
                            result = await asyncio.to_thread(
                                self.send_to_streamerbot,
                                donation["donor"], donation["amount"],
                                donation["currency"], donation["message"]
                            )
                            if not result["success"]:
                                logging.getLogger(__name__).error(
                                    "Донат не передан в Streamer.bot: %s", result["error"]
                                )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.is_connected = False
                self.last_error = str(exc)
                delay = reconnect_delays[reconnect_index]
                reconnect_index = min(reconnect_index + 1, len(reconnect_delays) - 1)
                logging.getLogger(__name__).exception(
                    "DonationAlerts reconnect in %ss", delay
                )
                await asyncio.sleep(delay)

    def start(self):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run_loop())


da_worker = DonationAlertsWorker()

