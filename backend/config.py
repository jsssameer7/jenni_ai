import os
from pathlib import Path
from typing import List, Dict
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR = DATA_DIR / "generated_images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "Jenni AI"
    APP_TITLE: str = "Jenni AI — Your Personal Assistant"
    VERSION: str = "1.0.0"
    
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Security & Auth
    # A persistent or configurable secret key for token verification
    SECRET_KEY: str = "jenni_ai_secret_key_change_me_in_production"
    # Token required by remote clients (e.g. Android phone over Tailscale)
    AUTH_TOKEN: str = "jenni-mobile-token-2026"
    REQUIRE_AUTH_FOR_LOCAL: bool = False  # Localhost is trusted by default
    REQUIRE_AUTH_FOR_REMOTE: bool = True  # Remote LAN/Tailscale must authenticate
    
    # Database
    DATABASE_PATH: Path = DATA_DIR / "jenni_ai.db"
    IMAGES_PATH: Path = IMAGES_DIR
    
    # AI Engine - Ollama
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT: float = 60.0
    
    # Optional Online AI Provider
    ONLINE_AI_PROVIDER: str = "none"  # "none", "openai", "groq"
    ONLINE_AI_API_KEY: str = ""
    ONLINE_AI_BASE_URL: str = "https://api.openai.com/v1"
    ONLINE_AI_MODEL: str = "gpt-4o-mini"
    
    # ComfyUI Image Generation
    COMFYUI_URL: str = "http://127.0.0.1:8188"
    
    # Speech / Voice
    DEFAULT_GREETING: str = "Hello! I'm Jenni AI. How can I help you today?"
    ENABLE_AUDIO_OUTPUT: bool = False
    TTS_RATE: int = 180
    TTS_VOLUME: float = 1.0
    DEFAULT_LANGUAGE: str = "en-US"
    
    # Safe PC Automation Controls
    SENSITIVE_ACTIONS_REQUIRE_CONFIRMATION: bool = True
    
    # Allowed applications map (normalized key -> binary or launch command)
    APPROVED_APPS: Dict[str, str] = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "vscode": "code",
        "code": "code",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "browser": "start",
        "edge": "msedge.exe",
        "paint": "mspaint.exe"
    }
    
    # Approved website domains for opening
    APPROVED_WEBSITES: List[str] = [
        "google.com",
        "youtube.com",
        "github.com",
        "wikipedia.org",
        "stackoverflow.com",
        "python.org",
        "fastapi.tiangolo.com",
        "reddit.com",
        "chatgpt.com",
        "ollama.com"
    ]
    
    # Approved search directories on Windows
    @property
    def approved_directories(self) -> List[Path]:
        user_home = Path.home()
        dirs = [
            BASE_DIR,
            user_home / "Desktop",
            user_home / "Documents",
            user_home / "Downloads"
        ]
        return [d for d in dirs if d.exists()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
