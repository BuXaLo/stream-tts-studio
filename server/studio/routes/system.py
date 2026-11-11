"""System configuration API routes."""
from fastapi import APIRouter, HTTPException


def create_system_router(load_config, save_config, get_file_lock, config_file, ws_manager, validate_host, validate_port):
    router = APIRouter()

    @router.get("/api/system_config")
    def api_get_system_config():
        cfg = load_config()
        return {
            "config": cfg,
            "obs_connected": len(ws_manager.active_connections) > 0,
            "active_connections_count": len(ws_manager.active_connections)
        }

    @router.post("/api/system_config")
    def api_save_system_config(data: dict):
        with get_file_lock(config_file):
            cfg = load_config()
            if "host" in data:
                cfg["host"] = validate_host(data["host"])
            if "port" in data:
                try:
                    port = validate_port(data["port"])
                except ValueError:
                    raise HTTPException(status_code=400, detail="Порт должен быть целым числом от 1 до 65535.")
                cfg["port"] = port
            if "n_timesteps" in data:
                try:
                    cfg["n_timesteps"] = max(4, min(15, int(data["n_timesteps"])))
                except (TypeError, ValueError, OverflowError):
                    raise HTTPException(status_code=400, detail="n_timesteps должен быть целым числом.")
            if "auto_open_browser" in data:
                cfg["auto_open_browser"] = bool(data["auto_open_browser"])
            save_config(cfg)
        return {"status": "ok", "config": cfg}

    return router
