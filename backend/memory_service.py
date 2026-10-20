import re
from typing import List, Dict, Any, Optional
from backend.database import (
    save_memory, 
    get_all_memories, 
    delete_memory, 
    delete_memory_by_key,
    is_sensitive_content
)

# Common memory trigger patterns
REMEMBER_PATTERNS = [
    r"remember\s+that\s+(?:i\s+(?:like|prefer|am|work\s+as|have)|my\s+([a-zA-Z0-9_\s]+)\s+is)\s+(.+)",
    r"remember(?:\s+to\s+call\s+me|:?\s+my\s+name\s+is)\s+([a-zA-Z0-9_\s]+)",
    r"remember\s+that\s+(.+)",
    r"save\s+to\s+memory[:\s]+(.+)",
    r"keep\s+in\s+mind\s+that\s+(.+)"
]

class MemoryService:
    @staticmethod
    def list_memories() -> List[Dict[str, Any]]:
        """Retrieve all stored user preferences and memories."""
        return get_all_memories()

    @staticmethod
    def add_or_update(key: str, value: str, category: str = "preference") -> Dict[str, Any]:
        """Manually store or update a memory."""
        if is_sensitive_content(key) or is_sensitive_content(value):
            raise ValueError("Jenni AI safety guard: Refusing to store passwords or API keys in memory.")
        return save_memory(key=key, value=value, category=category)

    @staticmethod
    def remove(memory_id: int) -> bool:
        """Remove a memory by ID."""
        return delete_memory(memory_id)

    @staticmethod
    def remove_by_key(key: str) -> bool:
        """Remove a memory by key."""
        return delete_memory_by_key(key)

    @staticmethod
    def extract_and_save_from_text(user_input: str) -> Optional[Dict[str, str]]:
        """
        Detects if user said "Remember that ..." or similar, and extracts the memory automatically.
        """
        text = user_input.strip()
        lower = text.lower()

        # Check for explicit remember intents
        for pat in REMEMBER_PATTERNS:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                captured = match.groups()
                if len(captured) == 1:
                    content = captured[0].strip()
                    # e.g., "my preferred language is Python"
                    key_val = re.split(r"\s+is\s+|\s+are\s+|\s*:\s*", content, maxsplit=1)
                    if len(key_val) == 2:
                        key, val = key_val[0].strip(), key_val[1].strip()
                    else:
                        key = f"note_{len(content[:15].replace(' ', '_'))}"
                        val = content
                elif len(captured) == 2:
                    key = captured[0].strip() if captured[0] else "preference"
                    val = captured[1].strip()
                else:
                    continue

                if not is_sensitive_content(key) and not is_sensitive_content(val):
                    try:
                        return save_memory(key=key, value=val, category="preference")
                    except Exception:
                        pass
        return None

    @staticmethod
    def build_memory_context() -> str:
        """Build a system prompt section containing all active user memories."""
        memories = get_all_memories()
        if not memories:
            return "No prior user preferences saved yet."
        
        lines = ["Current User Preferences & Memories:"]
        for m in memories:
            lines.append(f"- {m['key'].capitalize()}: {m['value']}")
        return "\n".join(lines)

memory_service = MemoryService()
