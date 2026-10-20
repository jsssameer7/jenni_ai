import os
import io
import wave
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
import pyttsx3
from backend.config import settings

class VoiceService:
    def __init__(self):
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", settings.TTS_RATE)
            self._engine.setProperty("volume", settings.TTS_VOLUME)
            # Prefer female voice (Zira) for Jenni AI if available
            voices = self._engine.getProperty("voices")
            for v in voices:
                if "zira" in v.name.lower() or "female" in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break
        except Exception as e:
            self._engine = None

    def get_status(self) -> Dict[str, Any]:
        """Return available voices and speech engine status."""
        voices_list = []
        if self._engine:
            try:
                for v in self._engine.getProperty("voices"):
                    voices_list.append({"id": v.id, "name": v.name, "languages": getattr(v, "languages", [])})
            except Exception:
                pass

        return {
            "tts_available": self._engine is not None,
            "tts_engine": "Windows SAPI5 (pyttsx3)",
            "voices": voices_list,
            "stt_engine": "Browser Web Speech API + Whisper Bridge",
            "supported_languages": [
                {"code": "en-US", "name": "English (US)"},
                {"code": "en-IN", "name": "English (India)"},
                {"code": "hi-IN", "name": "Hindi (India)"},
                {"code": "ta-IN", "name": "Tamil (India)"},
                {"code": "te-IN", "name": "Telugu (India)"},
                {"code": "bn-IN", "name": "Bengali (India)"}
            ]
        }

    def speak_locally(self, text: str) -> bool:
        """Speak out text directly through PC speakers."""
        if not self._engine:
            self._init_engine()
        if not self._engine:
            return False

        try:
            # Re-initialize to avoid comtypes event loop deadlock on repeated calls
            engine = pyttsx3.init()
            engine.setProperty("rate", settings.TTS_RATE)
            engine.setProperty("volume", settings.TTS_VOLUME)
            # Find Zira or first voice
            for v in engine.getProperty("voices"):
                if "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception:
            return False

    def synthesize_wav(self, text: str) -> Optional[Path]:
        """Synthesize text to a WAV audio file so web & mobile clients can stream it."""
        try:
            temp_path = settings.DATA_DIR / f"tts_{uuid.uuid4().hex[:8]}.wav"
            engine = pyttsx3.init()
            engine.setProperty("rate", settings.TTS_RATE)
            engine.setProperty("volume", settings.TTS_VOLUME)
            for v in engine.getProperty("voices"):
                if "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.save_to_file(text, str(temp_path))
            engine.runAndWait()
            if temp_path.exists() and temp_path.stat().st_size > 0:
                return temp_path
        except Exception:
            pass
        return None

voice_service = VoiceService()
