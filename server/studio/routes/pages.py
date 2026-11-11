"""Dashboard, overlay page and overlay WebSocket routes."""
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response


def create_pages_router(dashboard_dir, overlay_dir, ws_manager, same_origin):
    router = APIRouter()

    @router.get("/")
    def root():
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
    
    @router.get("/favicon.ico")
    def get_favicon():
        fav_path = os.path.join(DASHBOARD_DIR, "favicon.ico")
        if os.path.exists(fav_path):
            return FileResponse(fav_path)
        return Response(status_code=204)
    
    @router.get("/overlay")
    @router.get("/overlay/")
    def get_overlay_page():
        return FileResponse(os.path.join(OVERLAY_DIR, "overlay.html"))
    
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
