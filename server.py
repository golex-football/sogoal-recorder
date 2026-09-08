import asyncio
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    BITRATE_PRESETS,
    DEFAULT_OUTPUT_DIR,
    load_presets,
    save_presets,
)
from engine import RecordingManager, format_bytes

app = FastAPI(title="SoGoal Link Recorder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = RecordingManager(output_root=DEFAULT_OUTPUT_DIR)
active_websockets: List[WebSocket] = []

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


class StartRecordRequest(BaseModel):
    url: str
    season: str
    competition: str
    match_name: str
    bitrate_preset: str = "copy"
    capture_type: str = "auto"


class AddPresetRequest(BaseModel):
    type: str  # "season" or "competition"
    name: str


class PathActionRequest(BaseModel):
    path: Optional[str] = None


@app.get("/api/presets")
def get_presets():
    presets = load_presets()
    return {
        "seasons": presets["seasons"],
        "competitions": presets["competitions"],
        "bitrate_presets": BITRATE_PRESETS,
        "output_directory": str(DEFAULT_OUTPUT_DIR),
    }


@app.post("/api/presets")
def add_preset(req: AddPresetRequest):
    presets = load_presets()
    clean_name = req.name.strip().replace(" ", "_")
    if not clean_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    if req.type == "season":
        if clean_name not in presets["seasons"]:
            presets["seasons"].insert(0, clean_name)
    elif req.type == "competition":
        if clean_name not in presets["competitions"]:
            presets["competitions"].insert(0, clean_name)
    else:
        raise HTTPException(status_code=400, detail="Invalid preset type")

    save_presets(presets["seasons"], presets["competitions"])
    return {"status": "success", "presets": presets}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.post("/api/record/start")
async def start_recording(req: StartRecordRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Stream or page URL is required.")

    session_id = str(uuid.uuid4())[:8]
    session = manager.start_recording(
        session_id=session_id,
        url=url,
        season=req.season,
        competition=req.competition,
        match_name=req.match_name,
        bitrate_preset=req.bitrate_preset,
        capture_type=req.capture_type,
    )
    return {"status": "started", "session": session.to_dict()}


@app.post("/api/record/stop/{session_id}")
async def stop_recording(session_id: str):
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found.")
    await manager.stop_recording(session_id)
    return {"status": "stopping", "session": session.to_dict()}


@app.delete("/api/record/session/{session_id}")
async def dismiss_session(session_id: str):
    if session_id in manager.sessions:
        del manager.sessions[session_id]
    return {"status": "dismissed", "id": session_id}


@app.get("/api/recordings/active")
def get_active_recordings():
    return {"recordings": manager.get_all_sessions()}


@app.get("/api/recordings/library")
def get_library():
    """Scans the saved video recordings directory and returns hierarchy."""
    base = DEFAULT_OUTPUT_DIR
    if not base.exists():
        return {"items": []}

    results = []
    valid_exts = {".mp4", ".mkv", ".ts", ".m4a", ".webm", ".avi"}

    for root, _, files in os.walk(base):
        root_path = Path(root)
        for f in files:
            file_path = root_path / f
            if file_path.suffix.lower() in valid_exts:
                try:
                    stat = file_path.stat()
                    rel_parts = file_path.relative_to(base).parts
                    season = rel_parts[0] if len(rel_parts) > 1 else "General"
                    comp = rel_parts[1] if len(rel_parts) > 2 else "General"
                    match = rel_parts[2] if len(rel_parts) > 3 else "General"

                    results.append({
                        "name": f,
                        "path": str(file_path),
                        "folder": str(root_path),
                        "season": season,
                        "competition": comp,
                        "match": match,
                        "size_bytes": stat.st_size,
                        "size_formatted": format_bytes(stat.st_size),
                        "modified_timestamp": stat.st_mtime,
                        "modified_formatted": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    })
                except OSError:
                    continue

    results.sort(key=lambda x: x["modified_timestamp"], reverse=True)
    return {"items": results, "base_dir": str(base)}


@app.post("/api/system/open-folder")
def open_folder(req: PathActionRequest):
    target = req.path or str(DEFAULT_OUTPUT_DIR)
    target_path = Path(target)
    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["xdg-open", str(target_path)])
        return {"status": "opened", "path": str(target_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")


@app.post("/api/system/play")
def play_video(req: PathActionRequest):
    if not req.path or not os.path.exists(req.path):
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        subprocess.Popen(["xdg-open", req.path])
        return {"status": "playing", "path": req.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to play video: {e}")


@app.delete("/api/recordings/file")
def delete_file(req: PathActionRequest):
    if not req.path or not os.path.exists(req.path):
        raise HTTPException(status_code=404, detail="File does not exist.")
    # Ensure it is inside DEFAULT_OUTPUT_DIR for security
    file_path = Path(req.path).resolve()
    if not str(file_path).startswith(str(DEFAULT_OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Cannot delete files outside recording directory.")
    try:
        os.remove(file_path)
        return {"status": "deleted", "path": str(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            # Broadcast state
            data = {"recordings": manager.get_all_sessions()}
            await websocket.send_json(data)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


# Mount static assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "SoGoal Link Recorder Backend Running."}
