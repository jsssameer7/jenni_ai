import httpx
import json
import re
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
2. Tone: Friendly, articulate, concise, and helpful. You explain programming and technical concepts simply and clearly.
3. Capabilities: You can control approved PC applications (Calculator, Notepad, VS Code, File Explorer), search local files, manage persistent memories, generate images, and run automated workflows.
4. Privacy & Safety: You never ask for or store passwords or API keys. You respect system boundaries.

{memory_context}
"""

class AIService:
    @staticmethod
    async def get_models_status() -> Dict[str, Any]:
        """Check Ollama and available AI models."""
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
            "ollama_online": ollama_online,
            "ollama_url": settings.OLLAMA_BASE_URL,
            "default_model": settings.OLLAMA_MODEL,
            "installed_models": models,
            "online_provider": settings.ONLINE_AI_PROVIDER,
            "online_available": bool(settings.ONLINE_AI_API_KEY)
        }

    @staticmethod
    def detect_instant_intent(user_text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Fast intent recognition for instant PC actions (e.g. 'open calculator', 'launch notepad').
        Returns (action_type, execution_result) or None.
        """
        text = user_text.strip().lower()

        # 1. Open App Intent
        open_match = re.search(r"(?:open|launch|start|run)\s+(calculator|calc|notepad|vscode|vs code|code|explorer|file explorer|browser|paint)", text)
        if open_match:
            app_raw = open_match.group(1).replace("vs code", "vscode")
            res = pc_control_service.open_app(app_raw)
            return ("open_app", res)

        # 2. Open Website Intent
        web_match = re.search(r"(?:open|go to|browse|visit)\s+(https?://[^\s]+|[a-zA-Z0-9\-\.]+\.(?:com|org|io|net|edu|dev|ai))", text)
        if web_match:
            url = web_match.group(1)
            res = pc_control_service.open_website(url)
            return ("open_website", res)

        # 3. File Search Intent
        search_match = re.search(r"(?:find|search(?: for)?|locate)\s+(?:file|files|document|documents)?\s*(?:named|called)?\s*([a-zA-Z0-9_\-\.\*]+)", text)
        if search_match and len(search_match.group(1)) > 1:
            query = search_match.group(1).strip()
            # If query is a generic keyword, search files
            if query not in ["the", "me", "a", "an", "my"]:
                files = file_service.search_files(query=query, max_results=5)
                return ("file_search", {"query": query, "files": files})

        # 4. Generate Image Intent
        img_match = re.search(r"(?:generate|create|draw|make|paint)\s+(?:an?\s+)?(?:image|picture|photo|art|artwork|visual|illustration)\s+(?:of\s+)?(.+)", text)
        if img_match:
            prompt = img_match.group(1).strip()
            return ("generate_image", {"prompt": prompt})

        return None

    @staticmethod
    async def chat(
        user_message: str,
        session_id: str = "default",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process user message:
        1. Extract and store memories if user explicitly requested.
        2. Detect and execute instant PC/system intents if applicable.
        3. Call Ollama (or fallback) with conversational context.
        4. Record interaction in database.
        """
        model_name = model or settings.OLLAMA_MODEL

        # Step 1: Check if user asks to remember something
        saved_memory = memory_service.extract_and_save_from_text(user_message)

        # Step 2: Check for instant PC intents
        intent = AIService.detect_instant_intent(user_message)
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
        add_message(role="user", content=user_message, session_id=session_id, model=model_name)

        # Build prompt messages
        memory_ctx = memory_service.build_memory_context()
        system_content = SYSTEM_PROMPT_TEMPLATE.format(memory_context=memory_ctx)

        # Retrieve recent conversation turns
        recent_history = get_recent_messages(session_id=session_id, limit=8)

        ollama_messages = [{"role": "system", "content": system_content}]
        for turn in recent_history:
            ollama_messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })

        # Step 4: If an action was just executed, inform the LLM context so it responds naturally
        if executed_action:
            action_desc = f"[System Notification to Jenni AI]: You have successfully performed the action: {json.dumps(executed_action)}. Please confirm this politely to the user in your natural assistant tone."
            ollama_messages.append({"role": "system", "content": action_desc})

        # Step 5: Query Ollama
        ai_reply = ""
        model_used = model_name

        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
                res = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model_name,
                        "messages": ollama_messages,
                        "stream": False
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    ai_reply = data.get("message", {}).get("content", "").strip()
                else:
                    ai_reply = f"Jenni AI: Ollama returned status code {res.status_code}. Please make sure model '{model_name}' is loaded."
        except Exception as e:
            # Check online fallback if configured
            if settings.ONLINE_AI_PROVIDER == "openai" and settings.ONLINE_AI_API_KEY:
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{settings.ONLINE_AI_BASE_URL}/chat/completions",
                            headers={"Authorization": f"Bearer {settings.ONLINE_AI_API_KEY}"},
                            json={
                                "model": settings.ONLINE_AI_MODEL,
                                "messages": ollama_messages
                            }
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            ai_reply = data["choices"][0]["message"]["content"]
                            model_used = f"{settings.ONLINE_AI_MODEL} (Online)"
                except Exception as ex:
                    ai_reply = f"Jenni AI: Could not reach Ollama at {settings.OLLAMA_BASE_URL} or online provider. Error: {str(ex)}"
            else:
                ai_reply = f"Jenni AI: I am temporarily unable to connect to Ollama ({str(e)}). Please ensure Ollama is running with `ollama run qwen2.5:3b`."

        # If user explicitly requested to remember something, add a confirmation note
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

        # Generate clean spoken text for voice TTS (strip markdown and codeblocks)
        clean_spoken = re.sub(r"```[\s\S]*?```", "Code block omitted.", ai_reply)
        clean_spoken = re.sub(r"[\*\_#`]", "", clean_spoken).strip()
        # Keep spoken summary under 200 characters for snappy voice response
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
