"""DonationAlerts API and OAuth callback routes."""
import html
import json
import logging
import secrets
import time
import urllib.parse
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from studio.services.da_worker import DA_AUTH_URL, DA_SCOPES, DA_TOKEN_URL
from studio.services.donations import parse_donation

_OAUTH_STATES = {}

def create_donation_router(da_worker, load_da_config, save_da_config, load_da_tokens, save_da_tokens, get_file_lock, da_config_file, da_tokens_file, validate_streamerbot_url, logger=None):
    router = APIRouter()
    log = logger or logging.getLogger(__name__)

    @router.get("/api/da/config")
    def api_get_da_config():
        da_cfg = load_da_config()
        tokens = load_da_tokens()
        public_config = dict(da_cfg)
        client_secret_set = bool(public_config.get("client_secret"))
        public_config["client_secret"] = ""
        return {
            "config": public_config,
            "client_secret_set": client_secret_set,
            "has_tokens": tokens is not None,
            "redirect_uri": da_worker.get_redirect_uri(),
            "authorized_user": da_worker.authorized_user,
            "is_connected": da_worker.is_connected,
            "last_error": da_worker.last_error
        }
    
    @router.post("/api/da/config")
    def api_save_da_config(data: dict):
        with get_file_lock(da_config_file):
            da_cfg = load_da_config()
            if "enabled" in data: da_cfg["enabled"] = bool(data["enabled"])
            if "client_id" in data: da_cfg["client_id"] = str(data["client_id"]).strip()
            if str(data.get("client_secret", "")).strip(): da_cfg["client_secret"] = str(data["client_secret"]).strip()
            if "streamerbot_url" in data: da_cfg["streamerbot_url"] = validate_streamerbot_url(data["streamerbot_url"])
            if "streamerbot_action" in data:
                action = str(data["streamerbot_action"]).strip()
                if action.startswith("{"):
                    try:
                        parsed_action = json.loads(action)
                    except (TypeError, ValueError):
                        raise HTTPException(status_code=400, detail="Поле action содержит некорректный JSON.")
                    if not isinstance(parsed_action, dict):
                        raise HTTPException(status_code=400, detail="JSON action должен быть объектом.")
                da_cfg["streamerbot_action"] = action
            save_da_config(da_cfg)
        public_config = dict(da_cfg)
        public_config["client_secret"] = ""
        return {"status": "ok", "config": public_config, "client_secret_set": bool(da_cfg.get("client_secret"))}
    
    @router.get("/api/da/auth_url")
    def api_get_da_auth_url():
        da_cfg = load_da_config()
        client_id = da_cfg.get("client_id", "").strip()
        if not client_id:
            raise HTTPException(status_code=400, detail="Сначала укажите ID приложения в настройках!")
    
        redirect_uri = da_worker.get_redirect_uri()
        now = time.time()
        for old_state, expires_at in list(_OAUTH_STATES.items()):
            if expires_at <= now:
                _OAUTH_STATES.pop(old_state, None)
        state = secrets.token_urlsafe(32)
        _OAUTH_STATES[state] = now + 600
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": DA_SCOPES,
            "state": state
        }
        return {"auth_url": f"{DA_AUTH_URL}?{urllib.parse.urlencode(params)}"}
    
    @router.get("/api/da/callback")
    def api_da_callback(code: Optional[str] = None, error: Optional[str] = None, state: Optional[str] = None):
        expires_at = _OAUTH_STATES.pop(state, None) if state else None
        if not expires_at or expires_at <= time.time():
            return HTMLResponse("<h3>Ошибка авторизации DonationAlerts: недействительный или просроченный state.</h3>", status_code=400)
        if error:
            return HTMLResponse(f"<h3>Ошибка авторизации DonationAlerts: {html.escape(str(error))}</h3><p>Можете закрыть это окно.</p>")
        if not code:
            return HTMLResponse("<h3>Код авторизации не получен!</h3>")
    
        da_cfg = load_da_config()
        client_id = da_cfg.get("client_id", "").strip()
        client_secret = da_cfg.get("client_secret", "").strip()
        redirect_uri = da_worker.get_redirect_uri()
    
        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code
        }
        try:
            resp = requests.post(DA_TOKEN_URL, data=payload, timeout=10)
            if resp.status_code != 200:
                return HTMLResponse(f"<h3>Ошибка получения токена ({resp.status_code}): {html.escape(resp.text[:1000])}</h3>")
    
            tokens = resp.json()
            with get_file_lock(da_tokens_file):
                save_da_tokens(tokens)
            da_cfg["enabled"] = True
            with get_file_lock(da_config_file):
                save_da_config(da_cfg)
    
            return HTMLResponse("""
                <html>
                    <body style="background:#0b0a10; color:#10b981; font-family:sans-serif; text-align:center; padding:50px;">
                        <h2>✓ Успешная авторизация в DonationAlerts!</h2>
                        <p style="color:#eae8f0;">Токены сохранены. Слушатель активирован. Вы можете закрыть эту вкладку и вернуться в студию.</p>
                        <script>setTimeout(() => window.close(), 3000);</script>
                    </body>
                </html>
            """)
        except Exception as e:
            log.exception("DonationAlerts OAuth callback failed")
            return HTMLResponse(f"<h3>Исключение: {html.escape(str(e))}</h3>")
    
    @router.post("/api/da/test_donation")
    def api_test_da_donation(data: dict):
        donation = parse_donation(data)
        if donation is None:
            raise HTTPException(status_code=400, detail="Некорректные данные тестового доната.")
    
        result = da_worker.send_to_streamerbot(
            donation["donor"], donation["amount"],
            donation["currency"], donation["message"]
        )
        if not result["success"]:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Streamer.bot не принял тестовый донат.",
                    "status_code": result["status_code"],
                    "error": result["error"]
                }
            )
        return {
            "status": "ok",
            "result": result,
            "sent": {
                "donor": donation["donor"], "amount": donation["amount"],
                "currency": donation["currency"], "message": donation["message"]
            }
        }
    

    return router
