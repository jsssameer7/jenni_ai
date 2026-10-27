import httpx
import json
import uuid
import os
import random
import re
import socket
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from PIL import Image, ImageOps
import subprocess
from backend.config import settings

# Force IPv4 socket resolution on Windows to prevent Tailscale/IPv6 DNS hang
try:
    _orig_getaddrinfo = socket.getaddrinfo
    def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    socket.getaddrinfo = _getaddrinfo_ipv4
except Exception:
    pass

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

class ImageService:
    @staticmethod
    def get_gpu_vram() -> Dict[str, Any]:
        """Detect GPU model and VRAM."""
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                total_mb = int(parts[1])
                free_mb = int(parts[2])
                
                recommendation = "Stable Diffusion 1.5 / SD-Turbo / LCM (4GB VRAM: use --lowvram mode for ComfyUI)"
                if total_mb >= 8000:
                    recommendation = "SDXL / Flux-schnell / SD 1.5 (High VRAM available)"
                
                return {
                    "available": True,
                    "model": parts[0],
                    "total_vram_mb": total_mb,
                    "free_vram_mb": free_mb,
                    "recommendation": recommendation
                }
        except Exception:
            pass

        return {
            "available": False,
            "model": "Unknown / Integrated GPU",
            "total_vram_mb": 0,
            "free_vram_mb": 0,
            "recommendation": "Cloud Neural Synthesis (Fast SD / Pollinations)"
        }

    @staticmethod
    async def check_comfyui_status() -> Dict[str, Any]:
        """Check if ComfyUI local server is active."""
        gpu = ImageService.get_gpu_vram()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{settings.COMFYUI_URL}/system_stats")
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "online": True,
                        "url": settings.COMFYUI_URL,
                        "gpu": gpu,
                        "system": data
                    }
        except Exception:
            pass

        return {
            "online": False,
            "url": settings.COMFYUI_URL,
            "gpu": gpu,
            "message": "ComfyUI offline. Jenni AI is utilizing cloud neural synthesis."
        }

    @staticmethod
    def clean_prompt_for_generation(raw_prompt: str) -> str:
        """
        Cleans conversational prefix words while preserving the exact descriptive prompt.
        E.g.: 'create cat image' -> 'cat'
              'generate a cute cat on a car' -> 'a cute cat on a car'
        """
        p = raw_prompt.strip().strip('"\'')
        p = re.sub(
            r"^(?:please\s+)?(?:generate|create|draw|make|paint|synthesize|show\s+me)\s+(?:an?\s+)?",
            "",
            p,
            flags=re.IGNORECASE
        )
        p = re.sub(
            r"^(?:image|picture|photo|illustration|drawing|art|artwork|wallpaper)\s+(?:of|showing|depicting|about)\s+",
            "",
            p,
            flags=re.IGNORECASE
        )
        p = re.sub(
            r"\s+(?:image|picture|photo|illustration|drawing|art|artwork|wallpaper)$",
            "",
            p,
            flags=re.IGNORECASE
        )
        cleaned = p.strip()
        return cleaned if cleaned else raw_prompt.strip()

    @staticmethod
    def _save_processed_image(image_bytes: bytes, width: int, height: int, has_watermark_margin: bool = True) -> str:
        """
        Crops off the bottom watermark margin and resamples to width x height using Lanczos.
        Never saves blank cards or corrupt files.
        """
        img = Image.open(BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        orig_w, orig_h = img.size
        
        # Crop away bottom watermark margin
        if has_watermark_margin and orig_h > height:
            crop_bottom = min(orig_h, orig_h - 40)
            img = img.crop((0, 0, orig_w, crop_bottom))
        elif orig_h >= 120:
            img = img.crop((0, 0, orig_w, orig_h - 36))
                
        # Resize to requested dimensions with smooth Lanczos resampling
        img = ImageOps.fit(img, (width, height), Image.Resampling.LANCZOS)
        
        filename = f"jenni_ai_{uuid.uuid4().hex[:8]}.png"
        filepath = settings.IMAGES_PATH / filename
        settings.IMAGES_PATH.mkdir(parents=True, exist_ok=True)
        img.save(str(filepath), "PNG", quality=95)
        return filename

    @staticmethod
    async def generate_image(prompt: str, width: int = 512, height: int = 512) -> Dict[str, Any]:
        """
        Generates an AI image strictly based on the user's prompt without watermarks or blank cards.
        """
        gpu = ImageService.get_gpu_vram()
        comfy_status = await ImageService.check_comfyui_status()
        clean_p = ImageService.clean_prompt_for_generation(prompt)

        # 1. ComfyUI Local Pipeline
        if comfy_status["online"]:
            try:
                workflow = {
                    "3": {
                        "inputs": {
                            "seed": random.randint(1, 999999999),
                            "steps": 20,
                            "cfg": 7.0,
                            "sampler_name": "euler_ancestral",
                            "scheduler": "normal",
                            "denoise": 1.0,
                            "model": ["4", 0],
                            "positive": ["6", 0],
                            "negative": ["7", 0],
                            "latent_image": ["5", 0]
                        },
                        "class_type": "KSampler"
                    },
                    "4": {
                        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
                        "class_type": "CheckpointLoaderSimple"
                    },
                    "5": {
                        "inputs": {"width": width, "height": height, "batch_size": 1},
                        "class_type": "EmptyLatentImage"
                    },
                    "6": {
                        "inputs": {"text": clean_p, "clip": ["4", 1]},
                        "class_type": "CLIPTextEncode"
                    },
                    "7": {
                        "inputs": {"text": "blurry, low quality, deformed, distorted, watermark", "clip": ["4", 1]},
                        "class_type": "CLIPTextEncode"
                    },
                    "8": {
                        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                        "class_type": "VAEDecode"
                    },
                    "9": {
                        "inputs": {"filename_prefix": "JenniAI", "images": ["8", 0]},
                        "class_type": "SaveImage"
                    }
                }

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(f"{settings.COMFYUI_URL}/prompt", json={"prompt": workflow})
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "success": True,
                            "mode": "comfyui",
                            "prompt_id": data.get("prompt_id"),
                            "prompt": clean_p,
                            "message": f"Prompt '{clean_p}' submitted to local ComfyUI engine.",
                            "gpu": gpu
                        }
            except Exception:
                pass

        # 2. Neural Synthesis Engine (Watermark-free, exact prompt)
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://pollinations.ai/",
            "Origin": "https://pollinations.ai",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }

        # Candidate generation endpoints
        encoded = urllib.parse.quote(clean_p)
        seed = random.randint(1, 99999999)
        fetch_height = height + 40  # Extra margin for clean watermark cropping

        endpoints = [
            f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={fetch_height}&model=turbo&seed={seed}",
            f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={fetch_height}&seed={seed}",
            f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={fetch_height}&model=flux&seed={seed}"
        ]

        for url in endpoints:
            try:
                async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=headers) as client:
                    res = await client.get(url)
                    if res.status_code == 200 and len(res.content) > 3000:
                        filename = ImageService._save_processed_image(res.content, width, height, has_watermark_margin=True)
                        return {
                            "success": True,
                            "mode": "neural_ai",
                            "prompt": clean_p,
                            "filename": filename,
                            "url": f"/api/images/{filename}",
                            "message": f"Watermark-free AI image generated for '{clean_p}'.",
                            "gpu": gpu
                        }
            except Exception:
                continue

        # If generation could not complete, return a clean error without saving blank cards
        return {
            "success": False,
            "mode": "service_busy",
            "prompt": clean_p,
            "message": f"The neural generation service is momentarily busy. Please try generating '{clean_p}' again in a few moments.",
            "gpu": gpu
        }

    @staticmethod
    def list_images() -> List[Dict[str, Any]]:
        """List generated images saved in images folder, excluding any placeholder or notice cards."""
        results = []
        if not settings.IMAGES_PATH.exists():
            return []

        for f in sorted(settings.IMAGES_PATH.glob("*.png"), key=os.path.getmtime, reverse=True):
            if f.name.startswith("jenni_art_") or f.name.startswith("jenni_notice_"):
                continue  # Never display blank notice cards or old circles
            stat = f.stat()
            results.append({
                "filename": f.name,
                "url": f"/api/images/{f.name}",
                "size_kb": round(stat.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        return results

image_service = ImageService()
