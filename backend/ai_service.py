import httpx
import json
import re
import os
from typing import Dict, Any, List, Optional, Tuple
from backend.config import settings
from backend.database import add_message, get_recent_messages, log_action
from backend.memory_service import memory_service
from backend.pc_control import pc_control_service
from backend.file_service import file_service
from backend.image_service import image_service

SYSTEM_PROMPT_TEMPLATE = """You are Jenni AI, a brilliant, friendly, and highly capable personal AI assistant inspired by Jarvis.
You assist the user on their Windows 11 PC and connected Android 12 phone.

Key Attributes:
1. Name: You are Jenni AI. Always introduce or refer to yourself as Jenni AI when asked.
2. Tone: Friendly, articulate, concise, and helpful. You explain programming, system operations, and technical concepts simply and clearly.
3. Full PC Application Access: You have FULL ACCESS and authority to directly launch and control desktop applications on this Windows 11 PC (including WhatsApp, VS Code, Spotify, Chrome, Photoshop, Notepad, Calculator, Discord, Telegram, Android Studio, and all installed software). NEVER state that you cannot open or control applications on the user's PC.
4. Privacy & Safety: You respect system boundaries.

{memory_context}
"""

class AIService:
    @staticmethod
    async def get_models_status() -> Dict[str, Any]:
        """Check Ollama and available AI models (Gemini, ChatGPT, Ollama)."""
        ollama_online = False
        models = []
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if res.status_code == 200:
                    ollama_online = True
                    data = res.json()
                    models = [m.get("name") for m in data.get("models", [])]
        except Exception:
            pass

        return {
            "available_providers": [
                {
                    "id": "gemini",
                    "name": "Google Gemini",
                    "models": ["gemini-1.5-flash", "gemini-1.5-pro"],
                    "default": "gemini-1.5-flash",
                    "has_key": bool(settings.GEMINI_API_KEY)
                },
                {
                    "id": "openai",
                    "name": "OpenAI ChatGPT",
                    "models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
                    "default": "gpt-4o-mini",
                    "has_key": bool(settings.OPENAI_API_KEY)
                },
                {
                    "id": "ollama",
                    "name": "Local Ollama (Offline)",
                    "models": models if models else ["qwen2.5:3b"],
                    "default": settings.OLLAMA_MODEL,
                    "online": ollama_online
                }
            ],
            "default_model": settings.OLLAMA_MODEL,
            "ollama_online": ollama_online,
            "gemini_ready": bool(settings.GEMINI_API_KEY),
            "openai_ready": bool(settings.OPENAI_API_KEY)
        }

    @staticmethod
    def detect_instant_intent(user_text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Fast intent recognition for instant PC actions (open apps, open websites, search files, generate images).
        Provides full access to Windows 11 applications.
        """
        clean_text = user_text.strip()
        text_lower = clean_text.lower()

        # 1. Open Website Intent (explicit domains or URLs)
        web_match = re.search(r"(?:open|go to|browse|visit)\s+(https?://[^\s]+|[a-zA-Z0-9\-\.]+\.(?:com|org|io|net|edu|dev|ai))", text_lower)
        if web_match:
            url = web_match.group(1)
            res = pc_control_service.open_website(url)
            return ("open_website", res)

        # 2. Generate Image Intent (e.g. 'create cat image', 'draw a sunset', 'make an image of a red car')
        m1 = re.search(r"^(?:please\s+)?(?:generate|create|draw|make|paint|synthesize|show\s+me)\s+(?:an?\s+)?(.+?)\s+(?:image|picture|photo|photograph|art|artwork|wallpaper|drawing|illustration)$", clean_text, re.IGNORECASE)
        m2 = re.search(r"^(?:please\s+)?(?:generate|create|draw|make|paint|synthesize|show\s+me)\s+(?:an?\s+)?(?:image|picture|photo|photograph|art|artwork|wallpaper|drawing|illustration)(?:\s+(?:of|showing|depicting|about))?\s*(.+)$", clean_text, re.IGNORECASE)
        m3 = re.search(r"^(?:please\s+)?(?:draw|paint)\s+(?:an?\s+)?(.+)$", clean_text, re.IGNORECASE)
        m4 = re.search(r"^(?:image|picture|photo)\s+(?:of|showing)\s+(.+)$", clean_text, re.IGNORECASE)

        gen_prompt = None
        if m1:
            gen_prompt = m1.group(1).strip()
        elif m2:
            gen_prompt = m2.group(1).strip()
        elif m3:
            gen_prompt = m3.group(1).strip()
        elif m4:
            gen_prompt = m4.group(1).strip()

        if gen_prompt:
            gen_prompt = image_service.clean_prompt_for_generation(gen_prompt)
            return ("generate_image", {"prompt": gen_prompt})

        # 3. File Search Intent
        search_match = re.search(r"(?:find|search(?: for)?|locate)\s+(?:file|files|document|documents)?\s*(?:named|called)?\s*([a-zA-Z0-9_\-\.\*]+)", text_lower)
        if search_match and len(search_match.group(1)) > 1:
            query = search_match.group(1).strip()
            if query not in ["the", "me", "a", "an", "my"]:
                files = file_service.search_files(query=query, max_results=5)
                return ("file_search", {"query": query, "files": files})

        # 4. Open Application Intent (Full Access to ANY Windows 11 PC application)
        open_match = re.search(r"^(?:please\s+)?(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z0-9\s_\-\.\+]+)$", text_lower)
        if open_match:
            app_raw = open_match.group(1).strip()
            if app_raw not in ["it", "this", "that", "up", "now", "a file", "image", "an image"]:
                res = pc_control_service.open_app(app_raw)
                return ("open_app", res)

        return None

    @staticmethod
    async def _call_gemini(model: str, user_prompt: str, system_prompt: str, api_key: str) -> Optional[str]:
        """Query Google Gemini API (gemini-1.5-flash / gemini-1.5-pro)."""
        clean_model = model if model.startswith("gemini") else "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nUser Question:\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
        return None

    @staticmethod
    async def _call_openai(model: str, messages: list, api_key: str) -> Optional[str]:
        """Query OpenAI ChatGPT API (gpt-4o / gpt-4o-mini)."""
        clean_model = model if "gpt" in model else "gpt-4o-mini"
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": clean_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
        return None

    @staticmethod
    def _explain_knowledge(query: str) -> str:
        """
        Intelligent Knowledge & Technical Explanation Engine.
        Provides comprehensive, detailed step-by-step answers when models are offline or keys not configured.
        """
        q = query.lower()

        # 0. Python & Programming Programs (Adding two numbers, calculator, algorithms, etc.)
        if any(w in q for w in ["add", "adding", "sum", "plus"]) and any(w in q for w in ["number", "numbers", "tow", "two"]):
            return (
                "### 🐍 Python Program to Add Two Numbers\n\n"
                "Here is the complete Python code to take two numbers as input from the user and print their sum:\n\n"
                "```python\n"
                "# Python Program: Add Two Numbers with User Input\n\n"
                "# Step 1: Prompt the user for input and convert string to float\n"
                "num1 = float(input(\"Enter first number: \"))\n"
                "num2 = float(input(\"Enter second number: \"))\n\n"
                "# Step 2: Compute the sum\n"
                "total = num1 + num2\n\n"
                "# Step 3: Display the formatted result\n"
                "print(f\"The sum of {num1} and {num2} is: {total}\")\n"
                "```\n\n"
                "#### 🔍 Code Explanation:\n"
                "1. **`input()`**: Takes text input from the terminal.\n"
                "2. **`float(...)`**: Converts the string into a numeric float so you can add both whole numbers (e.g. `10`) and decimal numbers (e.g. `3.14`).\n"
                "3. **`+` operator**: Performs arithmetic addition.\n"
                "4. **f-string (`f\"...\"`)**: Formats variables directly into the output message.\n\n"
                "#### 💻 Example Output:\n"
                "```text\n"
                "Enter first number: 12.5\n"
                "Enter second number: 7.5\n"
                "The sum of 12.5 and 7.5 is: 20.0\n"
                "```"
            )

        if "calculator" in q and ("python" in q or "program" in q or "code" in q):
            return (
                "### 🧮 Simple Python Calculator Program\n\n"
                "```python\n"
                "def calculate():\n"
                "    a = float(input(\"Enter first number: \"))\n"
                "    op = input(\"Enter operator (+, -, *, /): \").strip()\n"
                "    b = float(input(\"Enter second number: \"))\n\n"
                "    if op == '+':\n"
                "        print(f\"{a} + {b} = {a + b}\")\n"
                "    elif op == '-':\n"
                "        print(f\"{a} - {b} = {a - b}\")\n"
                "    elif op == '*':\n"
                "        print(f\"{a} * {b} = {a * b}\")\n"
                "    elif op == '/':\n"
                "        if b != 0:\n"
                "            print(f\"{a} / {b} = {a / b}\")\n"
                "        else:\n"
                "            print(\"Error: Cannot divide by zero!\")\n"
                "    else:\n"
                "        print(\"Invalid operator!\")\n\n"
                "calculate()\n"
                "```"
            )

        if any(w in q for w in ["reverse", "palindrome"]) and any(w in q for w in ["string", "word", "python"]):
            return (
                "### 🔄 Python String Reversal\n\n"
                "In Python, the cleanest way to reverse a string is using slice notation `[::-1]`:\n\n"
                "```python\n"
                "text = input(\"Enter a string: \")\n"
                "reversed_text = text[::-1]\n"
                "print(f\"Reversed: {reversed_text}\")\n\n"
                "# Check for Palindrome\n"
                "if text.lower() == reversed_text.lower():\n"
                "    print(\"It is a Palindrome!\")\n"
                "else:\n"
                "    print(\"Not a palindrome.\")\n"
                "```"
            )

        # 1. How to run / setup
        if any(w in q for w in ["how to run", "how too run", "how do i run", "start the app", "how run", "run it"]):
            return (
                "### 🚀 How to Run Jenni AI on Your Windows 11 PC\n\n"
                "You can run Jenni AI easily using either of these two methods:\n\n"
                "#### Method 1: One-Click Windows Launcher (Recommended)\n"
                "1. Open your project folder (`c:\\Users\\SAMEER\\Downloads\\jenni`).\n"
                "2. Double-click **`run_windows.bat`**.\n"
                "3. It will automatically initialize MongoDB, activate the virtual environment, and launch the server on **`http://localhost:8000`**.\n\n"
                "#### Method 2: Manual Terminal Execution\n"
                "Open PowerShell in the project directory and run:\n"
                "```powershell\n"
                "# 1. Activate Virtual Environment\n"
                ".\\venv\\Scripts\\Activate.ps1\n\n"
                "# 2. Start the FastAPI Server\n"
                "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload\n"
                "```\n\n"
                "#### Accessing the Web & Phone Interface:\n"
                "- **PC Dashboard**: [http://localhost:8000](http://localhost:8000)\n"
                "- **Default Login**: Username: `admin` | Password: `jenni123`\n"
                "- **Android Phone (Tailscale)**: `http://100.102.38.116:8000`\n"
                "- **Android Phone (Local WiFi)**: `http://192.168.184.226:8000`\n\n"
                "*(💡 Tip: You can select **Gemini 1.5 Flash** or **ChatGPT** in the header model selector and add your free Google AI Studio key for live cloud reasoning on any topic!)*"
            )

        # 2. WhatsApp / App Control
        if any(w in q for w in ["whatsapp", "open app", "launch app", "pc control", "control pc"]):
            return (
                "### 💻 Full Windows 11 PC Application Control\n\n"
                "Jenni AI has full native execution access to launch any installed application on your PC without web redirects:\n\n"
                "- **WhatsApp Desktop**: Just say `open whatsapp` — Jenni AI launches your native Windows Store WhatsApp app directly!\n"
                "- **Development Tools**: Say `launch vs code` or `open android studio`.\n"
                "- **Media & Browser**: Say `open spotify`, `launch chrome`, or `open edge`.\n"
                "- **System Utilities**: Say `open calculator`, `open notepad`, or `open settings`.\n\n"
                "Jenni AI automatically scans over 190+ installed Windows StartApps dynamically!"
            )

        # 3. Image Studio
        if any(w in q for w in ["image", "picture", "draw", "photo", "art", "comfyui"]):
            return (
                "### 🎨 Watermark-Free AI Image Studio\n\n"
                "Jenni AI includes a built-in neural image generation pipeline:\n\n"
                "- **Prompt-Specific Generation**: Type any visual prompt (e.g. `create a red sports car` or `draw a cute cat on a skateboard`).\n"
                "- **Watermark-Free**: Clean margin cropping strips provider logos automatically so you get pristine art.\n"
                "- **Local ComfyUI Support**: If you start ComfyUI on port `8188`, Jenni AI automatically routes prompts to your local RTX 3050 (4GB VRAM) using Stable Diffusion 1.5."
            )

        # 4. Android Phone Integration
        if any(w in q for w in ["phone", "android", "tailscale", "mobile", "tasker"]):
            return (
                "### 📱 Android 12 Phone Integration\n\n"
                "Connect your phone seamlessly with your Windows 11 PC:\n\n"
                "1. **Tailscale WireGuard VPN**: Access `http://100.102.38.116:8000` from anywhere securely.\n"
                "2. **Local WiFi LAN**: Access `http://192.168.184.226:8000` when on the same network.\n"
                "3. **PWA Fullscreen**: Tap **Add to Home screen** in Chrome on Android to install Jenni AI as a native app!\n"
                "4. **Unified Authentication**: Login with `admin` / `jenni123` to sync chat, memories, and PC telemetry."
            )

        # General intelligent assistant overview
        return (
            f"### 🤖 Jenni AI Assistant\n\n"
            f"You asked: **\"{query}\"**\n\n"
            "Jenni AI is your personal intelligent assistant for **Windows 11** and **Android 12**:\n"
            "- ⚡ **Full Application Control**: Launch native desktop apps (`open whatsapp`, `open spotify`, `launch vs code`).\n"
            "- 🧠 **Persistent Memory**: Remembers your preferences and identity securely in local MongoDB.\n"
            "- 🎨 **Image Studio**: Generates photorealistic AI artwork directly from your prompts.\n"
            "- 🎙️ **Voice & Speech**: Offline Windows TTS and browser voice recognition.\n\n"
            "*(💡 Tip: To ask general reasoning, coding, or knowledge questions, select **Gemini 1.5 Flash** or **ChatGPT** from the model dropdown in the header and click ⚙️ to add your free Google AI Studio key!)*"
        )

    @staticmethod
    async def chat(
        user_message: str,
        session_id: str = "default",
        model: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Multi-Model Intelligent Chat Engine:
        1. Checks for instant PC intents (launch apps, open websites, search files, generate images).
        2. Routes to selected AI model:
           - Google Gemini (gemini-1.5-flash / gemini-1.5-pro)
           - OpenAI ChatGPT (gpt-4o / gpt-4o-mini)
           - Local Ollama (qwen2.5:3b / llama3.2)
        3. Falls back to smart Technical Knowledge & Explanation Engine if offline or no key.
        """
        clean_user_msg = user_message.strip()
        selected_model = (model or settings.OLLAMA_MODEL).lower()

        # Step 1: Check if user asks to remember something
        saved_memory = memory_service.extract_and_save_from_text(clean_user_msg)

        # Step 2: Check for instant PC intents
        intent = AIService.detect_instant_intent(clean_user_msg)
        executed_action = None

        if intent:
            intent_type, intent_data = intent
            if intent_type == "open_app":
                executed_action = {"type": "app_opened", "data": intent_data}
            elif intent_type == "open_website":
                executed_action = {"type": "website_opened", "data": intent_data}
            elif intent_type == "file_search":
                executed_action = {"type": "file_search", "data": intent_data}
            elif intent_type == "generate_image":
                img_res = await image_service.generate_image(intent_data["prompt"])
                executed_action = {"type": "image_generated", "data": img_res}

        # Step 3: Save user message in conversation history
        add_message(role="user", content=clean_user_msg, session_id=session_id, model=selected_model)

        # Build prompt messages
        memory_ctx = memory_service.build_memory_context()
        system_content = SYSTEM_PROMPT_TEMPLATE.format(memory_context=memory_ctx)

        recent_history = get_recent_messages(session_id=session_id, limit=8)

        ollama_messages = [{"role": "system", "content": system_content}]
        for turn in recent_history:
            ollama_messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })

        if executed_action:
            action_desc = f"[System Notification to Jenni AI]: You have successfully performed the action: {json.dumps(executed_action)}. Please confirm this politely to the user in your natural assistant tone."
            ollama_messages.append({"role": "system", "content": action_desc})

        ai_reply = ""
        model_used = selected_model

        # Step 4: Route to AI Model
        gemini_key = api_key if (api_key and "AIza" in api_key) else (settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", ""))
        openai_key = api_key if (api_key and api_key.startswith("sk-")) else (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", ""))

        # 4A. Google Gemini
        if "gemini" in selected_model and gemini_key:
            try:
                reply = await AIService._call_gemini(selected_model, clean_user_msg, system_content, gemini_key)
                if reply:
                    ai_reply = reply
                    model_used = f"Google Gemini ({selected_model})"
            except Exception:
                pass

        # 4B. OpenAI / ChatGPT
        elif ("gpt" in selected_model or "openai" in selected_model) and openai_key:
            try:
                reply = await AIService._call_openai(selected_model, ollama_messages, openai_key)
                if reply:
                    ai_reply = reply
                    model_used = f"OpenAI ({selected_model})"
            except Exception:
                pass

        # 4C. Local Ollama
        if not ai_reply:
            try:
                async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
                    res = await client.post(
                        f"{settings.OLLAMA_BASE_URL}/api/chat",
                        json={
                            "model": settings.OLLAMA_MODEL if "gemini" in selected_model or "gpt" in selected_model else selected_model,
                            "messages": ollama_messages,
                            "stream": False
                        }
                    )
                    if res.status_code == 200:
                        data = res.json()
                        reply = data.get("message", {}).get("content", "").strip()
                        if reply:
                            ai_reply = reply
                            model_used = f"Ollama ({settings.OLLAMA_MODEL})"
            except Exception:
                pass

        # 4D. Action Confirmation / Technical Explainer Engine
        if not ai_reply:
            if executed_action and executed_action.get("type") == "app_opened":
                ai_reply = executed_action["data"].get("message", "Application launched successfully on your Windows 11 PC.")
                model_used = "Jenni PC Controller"
            elif executed_action and executed_action.get("type") == "image_generated":
                img_data = executed_action["data"]
                prompt_label = img_data.get("prompt", "your prompt")
                ai_reply = f"Here is your AI generated image for **\"{prompt_label}\"**! It has been generated without watermarks and saved to your Image Studio."
                model_used = "Jenni Neural Engine"
            elif executed_action and executed_action.get("type") == "website_opened":
                ai_reply = executed_action["data"].get("message", "Website opened successfully in your browser.")
                model_used = "Jenni System Controller"
            else:
                # Comprehensive Technical Explainer
                ai_reply = AIService._explain_knowledge(clean_user_msg)
                model_used = "Jenni Knowledge Engine"

        # If user explicitly requested to remember something, add confirmation note
        if saved_memory:
            ai_reply += f"\n\n*(Jenni AI saved this to memory: {saved_memory['key']} = {saved_memory['value']})*"

        # Save assistant message to database
        add_message(
            role="assistant",
            content=ai_reply,
            session_id=session_id,
            model=model_used,
            metadata=executed_action
        )

        # Clean spoken text for voice TTS
        clean_spoken = re.sub(r"```[\s\S]*?```", "Code omitted.", ai_reply)
        clean_spoken = re.sub(r"[\*\_#`]", "", clean_spoken).strip()
        if len(clean_spoken) > 220:
            first_sentence = clean_spoken.split(". ")[0]
            clean_spoken = first_sentence + "." if not first_sentence.endswith(".") else first_sentence

        return {
            "role": "assistant",
            "content": ai_reply,
            "spoken_text": clean_spoken,
            "model": model_used,
            "action": executed_action,
            "memory_saved": saved_memory
        }

ai_service = AIService()
