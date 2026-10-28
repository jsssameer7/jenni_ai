# Jenni AI — Your Personal Assistant

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Live%20Showcase-38bdf8?style=for-the-badge&logo=github)](https://jsssameer7.github.io/jenni_ai/)
[![Ad Trailer](https://img.shields.io/badge/Official%20Trailer-Watch%20Online-a78bfa?style=for-the-badge&logo=youtube)](https://jsssameer7.github.io/jenni_ai/frontend/ad_video.html)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.115-059669?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![MongoDB](https://img.shields.io/badge/MongoDB-Local%20Atlas-47a248?style=for-the-badge&logo=mongodb)](https://mongodb.com)
[![Ollama](https://img.shields.io/badge/Ollama-Qwen2.5%3A3b-black?style=for-the-badge)](https://ollama.com)

> An intelligent, extensible AI assistant inspired by Jarvis, tailored for **Windows 11** PC and **Android 12** phone.

🌐 **Live Deployed Pages**:
- **Official Website & Feature Showcase**: [https://jsssameer7.github.io/jenni_ai/](https://jsssameer7.github.io/jenni_ai/)
- **Cinematic Interactive Ad Video**: [https://jsssameer7.github.io/jenni_ai/frontend/ad_video.html](https://jsssameer7.github.io/jenni_ai/frontend/ad_video.html)
- **Live Web Client Mockup**: [https://jsssameer7.github.io/jenni_ai/frontend/dashboard.html](https://jsssameer7.github.io/jenni_ai/frontend/dashboard.html)


Jenni AI combines local large language models (via **Ollama**), persistent SQLite memory, safe PC automation, offline Windows speech synthesis (**pyttsx3**), browser-based multi-language voice recognition (supporting English and Indian languages), **ComfyUI** image generation, and secure **Tailscale** private networking for your phone.

---

## 🌟 Highlights & Capabilities

- **Intelligent Assistant Persona**: Friendly, articulate, and natural assistant personality named **Jenni AI**. Answers general questions, explains code clearly, and manages PC tasks.
- **Local AI First**: Powered out of the box by local **Ollama** (`qwen2.5:3b`), running 100% offline and privately on your machine.
- **Persistent Personal Memory**: Remembers user preferences and facts (e.g. *"Remember that I prefer Python and dark mode"*). Includes a strict **Zero-Secrets Guard** that automatically blocks saving passwords or API keys.
- **Full Access PC Application Control**:
  - Direct execution of all Windows 11 desktop applications: **WhatsApp Desktop**, **Spotify**, **Google Chrome**, **VS Code**, **Photoshop**, **Android Studio**, **Discord**, **Telegram**, **Calculator**, **Notepad**, and all 190+ software detected via Windows `Get-StartApps`.
  - Protocol-level launching (`whatsapp:`, `spotify:`, `ms-settings:`) and native shell application handles.
  - Open approved websites (Google, GitHub, StackOverflow, etc.).
  - Search approved folders (Desktop, Documents, Downloads, Project) with path traversal protection.
  - Confirmation modals for sensitive actions.
  - **Zero unauthorized execution**: Never executes arbitrary AI terminal commands without explicit user approval.
- **Voice Assistant**:
  - Push-to-talk voice input with pulsing audio visualizer.
  - Configurable speech recognition supporting **English (US, India)** and **Indian languages (Hindi, Tamil, Telugu, Bengali)**.
  - Spoken answers aloud with offline Windows TTS (`pyttsx3` / SAPI5) and browser speech synthesis.
  - Mute / spoken response toggle and visible microphone status indicators.
- **Image Generation Studio**:
  - Integrates with local **ComfyUI** API (`http://127.0.0.1:8188`).
  - Automatically detects your GPU (**NVIDIA GeForce RTX 3050 Laptop with 4 GB VRAM**).
  - Recommends lightweight SD 1.5 / SD-Turbo models with `--lowvram` flag.
  - Built-in creative fallback visual generator when ComfyUI is offline.
- **Automated Multi-Step Workflows**:
  - Predefined workflows (Developer Workspace Launch, Daily Briefing, Deep System Health Check).
  - Live step progress tracking, stop/cancel controls, and action audit logs.
- **Android 12 Phone Integration**:
  - Fully responsive mobile interface.
  - Secure token authentication (`X-Jenni-Token`).
  - Works over **Tailscale** private network without opening ports to the public internet.
  - Optional **Tasker** webhook integration for custom phone automations.

---

## 💻 Hardware Verification & Model Recommendations

Jenni AI has been inspected and optimized for your specific hardware:
- **Operating System**: Windows 11 (64-bit)
- **System Memory**: 16 GB RAM
- **Dedicated GPU**: NVIDIA GeForce RTX 3050 Laptop GPU (**4096 MiB / 4 GB VRAM**)
- **Selected AI Model**: `qwen2.5:3b` in Ollama (1.9 GB download, ~2.5 GB RAM/VRAM footprint, under 3-second response latency).
- **Image Generation Recommendation**: SD 1.5 or SD-Turbo with `--lowvram` mode in ComfyUI for optimal 4GB VRAM performance.

---

## 📁 Project Structure

```
jenni/
│
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application & route endpoints
│   ├── config.py            # App configuration & environment settings
│   ├── database.py          # SQLite database schema, conversations & memories
│   ├── auth.py              # Token authentication & LAN/Tailscale detection
│   ├── ai_service.py        # Ollama LLM integration & natural intent detection
│   ├── memory_service.py    # Preference extraction & memory sanitization
│   ├── pc_control.py        # Safe Windows automation & allowlist controls
│   ├── file_service.py      # Secure approved folder search & reveal
│   ├── voice_service.py     # Offline Windows TTS (pyttsx3) & speech status
│   ├── image_service.py     # ComfyUI API integration & GPU VRAM analysis
│   └── task_service.py      # Multi-step task workflows engine
│
├── frontend/
│   ├── index.html           # Modern futuristic dashboard UI
│   ├── styles.css           # Obsidian/violet dark theme & animations
│   └── app.js               # Reactive client, speech, voice orb & API calls
│
├── tests/
│   ├── __init__.py
│   ├── test_api.py          # FastAPI endpoint integration tests
│   └── test_services.py     # Database, memory, PC control & safety tests
│
├── data/
│   ├── jenni_ai.db          # Persistent SQLite database (auto-created)
│   └── generated_images/    # Saved image generation output
│
├── .env.example             # Environment template
├── .env                     # Local configuration
├── .gitignore               # Git rules
├── requirements.txt         # Python package dependencies
├── run_windows.bat          # One-click Windows 11 launcher
└── README.md                # Documentation
```

---

## 🚀 Quickstart Guide

### Option 1: One-Click Windows Launcher (Easiest)
Simply double-click:
```bat
run_windows.bat
```
This automatically verifies the virtual environment, checks Ollama, launches the FastAPI server at `http://localhost:8000`, and opens your default browser!

---

### Option 2: Manual Terminal Setup

1. **Activate the virtual environment**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
   *(Or in Command Prompt: `.\venv\Scripts\activate.bat`)*

2. **Install requirements**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Ensure Ollama has the model downloaded**:
   ```powershell
   ollama pull qwen2.5:3b
   ```

4. **Start the Jenni AI Server**:
   ```powershell
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Open the Web Dashboard**:
   Navigate to [http://localhost:8000](http://localhost:8000) in your browser.

---

## 📱 Android 12 Phone Integration

Access Jenni AI on your Android 12 phone with zero router port forwarding:

1. **Install Tailscale**:
   - Install **Tailscale** on your Windows 11 PC and from the Google Play Store on your Android phone.
   - Sign into the same Tailscale account on both devices.
2. **Retrieve PC Tailscale IP**:
   - Open Tailscale on PC or look at the **Android Connect** tab in the Jenni AI dashboard. Note the `100.x.y.z` IP address.
3. **Open Jenni AI on Phone**:
   - In Chrome on Android, navigate to:
     ```
     http://<PC_TAILSCALE_IP>:8000?token=jenni-mobile-token-2026
     ```
4. **Install as App (PWA)**:
   - In Chrome, tap the 3 dots menu and select **"Add to Home screen"**. Jenni AI will now open fullscreen just like a native Android app!

### Tasker Android Automation (Optional)
Send voice commands or triggers from Tasker on Android:
- **Action**: HTTP Request
- **Method**: `POST`
- **URL**: `http://<PC_TAILSCALE_IP>:8000/api/chat`
- **Headers**:
  ```
  Content-Type: application/json
  X-Jenni-Token: jenni-mobile-token-2026
  ```
- **Body**: `{"message": "%VOICE_INPUT"}`

---

## 🎨 ComfyUI Image Generation Setup (Optional)

1. Download ComfyUI standalone for Windows.
2. Because your RTX 3050 has 4 GB VRAM, launch ComfyUI using the `--lowvram` flag:
   ```bat
   run_nvidia_gpu.bat --lowvram
   ```
3. Place a Stable Diffusion 1.5 checkpoint (e.g. `v1-5-pruned-emaonly.safetensors`) in `ComfyUI/models/checkpoints/`.
4. Ensure ComfyUI runs on `http://127.0.0.1:8188`.
5. In Jenni AI's **Image Studio** tab, prompts will now automatically generate using local Stable Diffusion! When ComfyUI is not running, Jenni AI automatically switches to its creative visual synth fallback.

---

## 🛡️ Security & Privacy Guarantees

- **No Public Exposure**: The server binds locally or over your private Tailscale mesh.
- **Authentication**: Remote endpoints require `X-Jenni-Token` or Bearer token header.
- **Allowlisted Execution**: Only approved executables (`calc.exe`, `notepad.exe`, `code`, `explorer.exe`, `mspaint.exe`) and approved domains can be launched.
- **Path Traversal Protection**: File searches and open commands are strictly confined to approved directories (`Desktop`, `Documents`, `Downloads`, `Project`).
- **Confirmation Gateway**: Sensitive operations trigger an explicit security confirmation modal in the UI.
- **Zero Secrets in Memory**: Regex security filters actively reject saving passwords, API keys, tokens, or private keys.

---

## 🧪 Running Automated Tests

Run the test suite with pytest:
```powershell
.\venv\Scripts\pytest -o pythonpath=. -v tests/
```

All 11 unit and integration tests will execute, verifying database storage, memory sanitization, PC allowlist enforcement, path traversal defense, and API endpoints.

---

*Enjoy pairing with Jenni AI — Your Personal Assistant!*
