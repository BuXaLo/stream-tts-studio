"""Custom font listing and upload routes."""
import os
import re
import time

from fastapi import APIRouter, File, HTTPException, UploadFile


def create_fonts_router(custom_fonts_dir, write_bytes_atomic):
    router = APIRouter()

    @router.get("/api/fonts")
    def api_get_fonts():
        custom_list = []
        if os.path.exists(custom_fonts_dir):
            for f in sorted(os.listdir(custom_fonts_dir)):
                if f.lower().endswith(('.ttf', '.otf', '.woff2', '.woff')):
                    font_name = os.path.splitext(f)[0]
                    custom_list.append({
                        "name": font_name,
                        "file": f,
                        "url": f"/fonts/custom/{f}"
                    })
        return {"custom_fonts": custom_list}
    
    @router.post("/api/upload_font")
    def api_upload_font(file: UploadFile = File(...)):
        filename = file.filename or ""
        raw_name, ext = os.path.splitext(filename)
        ext = ext.lower()
        allowed_exts = ['.ttf', '.otf', '.woff2', '.woff']
        if ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"Поддерживаются только форматы: {', '.join(allowed_exts)}")
    
        clean_base = re.sub(r'[^a-zA-Z0-9_\-\s]', '', raw_name).strip()
        if not clean_base:
            clean_base = f"font_{int(time.time())}"
    
        final_filename = f"{clean_base}{ext}"
        dest_path = os.path.join(custom_fonts_dir, final_filename)
        if os.path.exists(dest_path):
            is_duplicate = True
        else:
            write_bytes_atomic(dest_path, file.file.read())
            is_duplicate = False
    
        return {
            "status": "ok",
            "name": clean_base,
            "file": final_filename,
            "url": f"/fonts/custom/{final_filename}",
            "is_duplicate": is_duplicate
        }
    

    return router
