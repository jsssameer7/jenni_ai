import os
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.config import settings
from backend.database import (
    init_db,
    get_recent_messages,
    clear_conversation_history,
    get_recent_action_logs
)
from backend.auth import verify_auth, get_lan_and_tailscale_ips
from backend.ai_service import ai_service
from backend.memory_service import memory_service
from backend.pc_control import pc_control_service
from backend.file_service import file_service
from backend.voice_service import voice_service
from backend.image_service import image_service
from backend.task_service import task_service

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("=" * 60)
    print(f"  {settings.APP_TITLE} (v{settings.VERSION}) initialized.")
    print(f"  Ollama URL: {settings.OLLAMA_BASE_URL} (Model: {settings.OLLAMA_MODEL})")
    print(f"  Web Dashboard: http://localhost:{settings.PORT}")
    ips = get_lan_and_tailscale_ips()
    for item in ips:
        print(f"  Phone Access ({item['type']}): http://{item['ip']}:{item['port']}?token={settings.AUTH_TOKEN}")
    print("=" * 60)
    yield

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_TITLE,
    description="Backend API for Jenni AI — Your Personal Assistant",
    version=settings.VERSION,
    lifespan=lifespan
)

# Enable CORS for local and Android network connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Request Models ---
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    model: Optional[str] = None

class MemoryRequest(BaseModel):
    key: str
    value: str
    category: Optional[str] = "preference"

class AppRequest(BaseModel):
    app_name: str

class WebsiteRequest(BaseModel):
    url: str

class ConfirmationRequest(BaseModel):
    confirmation_id: str
    approved: bool

class FileOpenRequest(BaseModel):
    path: str
    reveal: Optional[bool] = False

class VoiceSpeakRequest(BaseModel):
    text: str

class ImageGenerateRequest(BaseModel):
    prompt: str
    width: Optional[int] = 512
    height: Optional[int] = 512

class TaskRunRequest(BaseModel):
    workflow_id: str

class TaskCancelRequest(BaseModel):
    task_id: str

# --- Endpoints ---

@app.get("/api/status")
async def get_system_status():
    """System health check and network discovery."""
    ai_status = await ai_service.get_models_status()
    gpu_status = image_service.get_gpu_vram()
    network_ips = get_lan_and_tailscale_ips()
    return {
        "title": settings.APP_TITLE,
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "greeting": settings.DEFAULT_GREETING,
        "ai": ai_status,
        "gpu": gpu_status,
        "network": network_ips,
        "auth_required_for_remote": settings.REQUIRE_AUTH_FOR_REMOTE,
        "token": settings.AUTH_TOKEN
    }

# 1. Chat Endpoints
@app.post("/api/chat", dependencies=[Depends(verify_auth)])
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    res = await ai_service.chat(
        user_message=req.message,
        session_id=req.session_id or "default",
        model=req.model
    )
    return res

@app.get("/api/chat/history", dependencies=[Depends(verify_auth)])
async def get_chat_history(session_id: str = "default", limit: int = 30):
    return get_recent_messages(session_id=session_id, limit=limit)

@app.delete("/api/chat/history", dependencies=[Depends(verify_auth)])
async def clear_chat(session_id: str = "default"):
    count = clear_conversation_history(session_id=session_id)
    return {"success": True, "deleted_count": count, "message": f"Cleared chat history for {session_id}."}

# 2. Personal Memory Endpoints
@app.get("/api/memory", dependencies=[Depends(verify_auth)])
async def list_memories():
    return memory_service.list_memories()

@app.post("/api/memory", dependencies=[Depends(verify_auth)])
async def add_memory(req: MemoryRequest):
    try:
        res = memory_service.add_or_update(key=req.key, value=req.value, category=req.category or "preference")
        return {"success": True, "memory": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/memory/{memory_id}", dependencies=[Depends(verify_auth)])
async def remove_memory(memory_id: int):
    success = memory_service.remove(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory item not found.")
    return {"success": True, "message": "Memory removed."}

# 3. PC Control Endpoints
@app.get("/api/pc/status", dependencies=[Depends(verify_auth)])
async def get_pc_metrics():
    return pc_control_service.get_system_status()

@app.post("/api/pc/app", dependencies=[Depends(verify_auth)])
async def launch_app(req: AppRequest):
    return pc_control_service.open_app(req.app_name)

@app.post("/api/pc/website", dependencies=[Depends(verify_auth)])
async def open_web(req: WebsiteRequest):
    return pc_control_service.open_website(req.url)

@app.post("/api/pc/confirm", dependencies=[Depends(verify_auth)])
async def confirm_action(req: ConfirmationRequest):
    return pc_control_service.resolve_confirmation(req.confirmation_id, req.approved)

@app.get("/api/pc/logs", dependencies=[Depends(verify_auth)])
async def get_action_audit_logs():
    return get_recent_action_logs(limit=30)

# 4. File Management & Search
@app.get("/api/files/search", dependencies=[Depends(verify_auth)])
async def search_files(
    query: str = Query("", description="Filename keyword to search for"),
    folder: Optional[str] = Query(None, description="Approved folder to restrict search"),
    extension: Optional[str] = Query(None, description="Filter by extension e.g. .py or .pdf")
):
    return file_service.search_files(query=query, folder=folder, extension=extension)

@app.post("/api/files/open", dependencies=[Depends(verify_auth)])
async def open_file(req: FileOpenRequest):
    return file_service.open_or_reveal_file(req.path, reveal=bool(req.reveal))

# 5. Voice & Speech Endpoints
@app.get("/api/voice/status", dependencies=[Depends(verify_auth)])
async def get_voice_status():
    return voice_service.get_status()

@app.post("/api/voice/speak", dependencies=[Depends(verify_auth)])
async def speak_text(req: VoiceSpeakRequest):
    success = voice_service.speak_locally(req.text)
    return {"success": success, "message": "Spoken through PC speakers." if success else "Speech engine error."}

@app.post("/api/voice/synthesize", dependencies=[Depends(verify_auth)])
async def synthesize_speech(req: VoiceSpeakRequest):
    wav_path = voice_service.synthesize_wav(req.text)
    if wav_path and wav_path.exists():
        return {"success": True, "audio_url": f"/api/voice/audio/{wav_path.name}"}
    return {"success": False, "message": "Could not synthesize audio file."}

@app.get("/api/voice/audio/{filename}")
async def get_audio_file(filename: str):
    file_path = settings.DATA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(file_path, media_type="audio/wav")

# 6. Image Generation Endpoints
@app.get("/api/images/status", dependencies=[Depends(verify_auth)])
async def get_images_status():
    return await image_service.check_comfyui_status()

@app.post("/api/images/generate", dependencies=[Depends(verify_auth)])
async def generate_image_endpoint(req: ImageGenerateRequest):
    return await image_service.generate_image(prompt=req.prompt, width=req.width or 512, height=req.height or 512)

@app.get("/api/images/list", dependencies=[Depends(verify_auth)])
async def list_generated_images():
    return image_service.list_images()

@app.get("/api/images/{filename}")
async def get_image_file(filename: str):
    img_path = settings.IMAGES_PATH / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(img_path)

# 7. Automated Tasks Endpoints
@app.get("/api/tasks/workflows", dependencies=[Depends(verify_auth)])
async def get_workflows():
    return task_service.list_workflows()

@app.get("/api/tasks/history", dependencies=[Depends(verify_auth)])
async def get_task_history():
    return task_service.get_task_history()

@app.post("/api/tasks/run", dependencies=[Depends(verify_auth)])
async def run_task(req: TaskRunRequest):
    return await task_service.run_workflow(req.workflow_id)

@app.post("/api/tasks/cancel", dependencies=[Depends(verify_auth)])
async def cancel_task(req: TaskCancelRequest):
    return task_service.cancel_task(req.task_id)

# 8. Mobile & Android Integration Info
@app.get("/api/mobile/info", dependencies=[Depends(verify_auth)])
async def get_mobile_integration_info():
    ips = get_lan_and_tailscale_ips()
    urls = [f"http://{item['ip']}:{item['port']}?token={settings.AUTH_TOKEN}" for item in ips]
    return {
        "title": "Jenni AI Android Integration Guide",
        "tailscale_steps": [
            "1. Install Tailscale on your Windows PC and Android 12 phone from Google Play Store.",
            "2. Sign in with the same Tailscale account on both devices.",
            "3. Note your PC's Tailscale 100.x.y.z IP address.",
            "4. Open Chrome on Android and visit: http://<PC_TAILSCALE_IP>:8000?token=" + settings.AUTH_TOKEN,
            "5. Tap 'Add to Home screen' in Chrome to install Jenni AI as a PWA / fullscreen app!"
        ],
        "tasker_integration": {
            "description": "Send voice or trigger commands directly from Tasker to your Jenni AI server.",
            "endpoint": "/api/chat",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "X-Jenni-Token": settings.AUTH_TOKEN
            },
            "sample_body": {"message": "%VOICE_INPUT"}
        },
        "connection_urls": urls,
        "token": settings.AUTH_TOKEN
    }

# 9. Serve Frontend
FRONTEND_DIR = settings.BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def serve_landing():
    """Serve the public-facing landing page website."""
    landing_file = FRONTEND_DIR / "landing.html"
    if landing_file.exists():
        return FileResponse(landing_file)
    # Fallback to dashboard if landing page doesn't exist yet
    dashboard_file = FRONTEND_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    return {"message": f"{settings.APP_TITLE} is running. Frontend not yet created."}

@app.get("/app")
async def serve_app():
    """Serve the main Jenni AI dashboard application."""
    dashboard_file = FRONTEND_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    return {"message": f"{settings.APP_TITLE} dashboard is loading..."}
