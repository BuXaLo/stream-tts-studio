"""Dashboard, overlay page and overlay WebSocket routes."""
import asyncio
import ipaddress
import os
import queue

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response


def create_pages_router(dashboard_dir, overlay_dir, ws_manager, same_origin):
    router = APIRouter()
    from studio.core import monitor

    @router.get("/monitor")
    @router.get("/monitor/")
    def get_monitor_page():
        monitor_file = os.path.join(os.path.dirname(dashboard_dir), "monitor", "index.html")
        return FileResponse(monitor_file)

    @router.get("/monitor/{asset_name}")
    def get_monitor_asset(asset_name: str):
        if asset_name not in {"app.js", "style.css"}:
            raise HTTPException(status_code=404, detail="Файл монитора не найден.")
        asset_file = os.path.join(os.path.dirname(dashboard_dir), "monitor", asset_name)
        return FileResponse(asset_file)

    @router.websocket("/ws/monitor")
    async def websocket_monitor(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host", "")
        if origin and not same_origin(origin, host, websocket.url.scheme):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        events = monitor.subscribe()
        try:
            for event in monitor.history():
                await websocket.send_json(event)
            while True:
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.25)
                    continue
                await websocket.send_json(event)
                if event.get("type") == "shutdown":
                    await websocket.close(code=1001)
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            monitor.unsubscribe(events)

    @router.post("/api/monitor/shutdown")
    async def shutdown_monitor(request: Request):
        client_host = request.client.host if request.client else ""
        request_host = request.url.hostname or ""
        try:
            client_is_local = ipaddress.ip_address(client_host).is_loopback
        except ValueError:
            client_is_local = False
        try:
            host_is_local = ipaddress.ip_address(request_host).is_loopback
        except ValueError:
            host_is_local = request_host.lower() == "localhost"
        if not client_is_local or not host_is_local:
            raise HTTPException(status_code=403, detail="Команда доступна только через локальный адрес студии.")
        if not monitor.schedule_shutdown():
            raise HTTPException(status_code=503, detail="Штатное выключение сейчас недоступно.")
        return {"status": "shutting_down"}

    @router.get("/")
    def root():
        return FileResponse(os.path.join(dashboard_dir, "index.html"))
    
    @router.get("/favicon.ico")
    def get_favicon():
        fav_path = os.path.join(dashboard_dir, "favicon.ico")
        if os.path.exists(fav_path):
            return FileResponse(fav_path)
        return Response(status_code=204)
    
    @router.get("/overlay")
    @router.get("/overlay/")
    def get_overlay_page():
        return FileResponse(os.path.join(overlay_dir, "overlay.html"))
    
    @router.websocket("/ws/overlay")
    async def websocket_overlay(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host", "")
        if origin and not same_origin(origin, host, websocket.url.scheme):
            await websocket.close(code=1008)
            return
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception:
            ws_manager.disconnect(websocket)
    

    return router
