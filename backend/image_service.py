import httpx
import json
import uuid
import os
import random
import re
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps
import subprocess
from backend.config import settings

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
                
                recommendation = "Stable Diffusion 1.5 / SD-Turbo / LCM (4GB VRAM detected: use --lowvram mode for ComfyUI)"
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
            "recommendation": "Use Cloud Neural Synthesis (Pollinations / Fast SD)"
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
            "message": "ComfyUI offline. Jenni AI is utilizing cloud neural synthesis (Fast SD / Pollinations Turbo)."
        }

    @staticmethod
    def clean_prompt_for_generation(raw_prompt: str) -> str:
        """
        Cleans user conversational phrasing into a crisp descriptive visual prompt.
        E.g.: 'create cat image' -> 'cat'
              'generate an image of a red sports car' -> 'red sports car'
        """
        p = raw_prompt.strip().strip('"\'')
        
        # Remove leading request verbs
        p = re.sub(
            r"^(?:please\s+)?(?:generate|create|draw|make|paint|synthesize|show\s+me)\s+(?:an?\s+)?",
            "",
            p,
            flags=re.IGNORECASE
        )
        
        # Remove phrases like 'image of', 'picture of', 'photo of'
        p = re.sub(
            r"^(?:image|picture|photo|illustration|drawing|art|artwork|wallpaper)\s+(?:of|showing|depicting|about)\s+",
            "",
            p,
            flags=re.IGNORECASE
        )
        
        # Remove trailing nouns if preceded by something, e.g. 'cat image' -> 'cat'
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
        Opens raw image bytes, cleanly removes any watermark/logo in the bottom margin,
        fits image to exact width x height, and saves as pristine PNG.
        """
        img = Image.open(BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        orig_w, orig_h = img.size
        
        # 1. If fetched with an extra margin at the bottom (where pollinations stamps its watermark)
        if has_watermark_margin and orig_h > height:
            # Crop away the bottom extra margin entirely
            img = img.crop((0, 0, orig_w, orig_h - (orig_h - height)))
        else:
            # If image matches exact height, trim bottom 36px to strip any corner logo, then resize back
            if orig_h >= 120:
                img = img.crop((0, 0, orig_w, orig_h - 36))
                
        # 2. Fit image to requested dimensions with smooth Lanczos resampling
        img = ImageOps.fit(img, (width, height), Image.Resampling.LANCZOS)
        
        filename = f"jenni_ai_{uuid.uuid4().hex[:8]}.png"
        filepath = settings.IMAGES_PATH / filename
        settings.IMAGES_PATH.mkdir(parents=True, exist_ok=True)
        img.save(str(filepath), "PNG", quality=95)
        return filename

    @staticmethod
    async def _fetch_from_wikimedia(query: str, width: int, height: int) -> Optional[str]:
        """Fetch matching real photograph from Wikimedia Commons as reliable visual fallback."""
        try:
            search_query = query.strip()
            words = search_query.split()
            if len(words) > 4:
                search_query = " ".join(words[:4])
                
            api_url = (
                f"https://commons.wikimedia.org/w/api.php?action=query"
                f"&generator=search&gsrnamespace=6&gsrsearch={urllib.parse.quote(search_query)}"
                f"&gsrlimit=3&prop=imageinfo&iiprop=url&format=json"
            )
            
            headers = {"User-Agent": USER_AGENT}
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
                res = await client.get(api_url)
                if res.status_code == 200:
                    data = res.json()
                    pages = data.get("query", {}).get("pages", {})
                    for _, pdata in pages.items():
                        infos = pdata.get("imageinfo", [])
                        if infos and "url" in infos[0]:
                            img_url = infos[0]["url"]
                            if any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                                img_res = await client.get(img_url)
                                if img_res.status_code == 200 and len(img_res.content) > 5000:
                                    return ImageService._save_processed_image(img_res.content, width, height, has_watermark_margin=False)
        except Exception:
            pass
        return None

    @staticmethod
    def generate_offline_notice(prompt: str, width: int = 512, height: int = 512) -> str:
        """
        Creates an informative offline status card when all network endpoints are unreachable.
        Clearly informs user without deceptive abstract circles.
        """
        filename = f"jenni_notice_{uuid.uuid4().hex[:8]}.png"
        filepath = settings.IMAGES_PATH / filename
        settings.IMAGES_PATH.mkdir(parents=True, exist_ok=True)

        img = Image.new("RGB", (width, height), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Card container
        pad = 24
        draw.rounded_rectangle(
            [pad, pad, width - pad, height - pad],
            radius=16,
            fill=(24, 30, 52),
            outline=(56, 189, 248),
            width=2
        )

        draw.text((pad + 24, pad + 30), "Jenni AI Image Studio", fill=(56, 189, 248))
        draw.text((pad + 24, pad + 60), f"Prompt: {prompt[:40]}", fill=(240, 245, 255))
        draw.text((pad + 24, pad + 100), "Status: Network Offline", fill=(244, 63, 94))
        draw.text((pad + 24, pad + 130), "Live neural generation requires active internet", fill=(148, 163, 184))
        draw.text((pad + 24, pad + 155), "or a running local ComfyUI instance (port 8188).", fill=(148, 163, 184))

        img.save(str(filepath), "PNG")
        return filename

    @staticmethod
    async def generate_image(prompt: str, width: int = 512, height: int = 512) -> Dict[str, Any]:
        """
        Multi-tier watermark-free prompt-based image generation pipeline:
        1. ComfyUI Local Server (if online)
        2. Pollinations AI Turbo Neural Generator (Fast SD, photorealistic, watermark stripped)
        3. Pollinations AI Default Neural Generator (High-fidelity SDXL, watermark stripped)
        4. Wikimedia Photographic Knowledge Search (Genuine photo matching prompt)
        5. Clean offline notice card (if completely disconnected)
        """
        gpu = ImageService.get_gpu_vram()
        comfy_status = await ImageService.check_comfyui_status()
        clean_prompt = ImageService.clean_prompt_for_generation(prompt)

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
                        "inputs": {"text": clean_prompt, "clip": ["4", 1]},
                        "class_type": "CLIPTextEncode"
                    },
                    "7": {
                        "inputs": {"text": "blurry, low quality, deformed, distorted, watermark, logo", "clip": ["4", 1]},
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
                            "prompt": clean_prompt,
                            "message": f"Prompt '{clean_prompt}' submitted to local ComfyUI engine.",
                            "gpu": gpu
                        }
            except Exception:
                pass

        # 2. Pollinations AI Turbo (Watermark-free by requesting extra height margin and cropping it off)
        try:
            encoded = urllib.parse.quote(clean_prompt)
            seed = random.randint(1, 99999999)
            # Request extra 40px at the bottom where watermark is placed
            turbo_url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height + 40}&model=turbo&seed={seed}"
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            }
            async with httpx.AsyncClient(timeout=18.0, follow_redirects=True, headers=headers) as client:
                res = await client.get(turbo_url)
                if res.status_code == 200 and len(res.content) > 2000:
                    filename = ImageService._save_processed_image(res.content, width, height, has_watermark_margin=True)
                    return {
                        "success": True,
                        "mode": "neural_turbo",
                        "prompt": clean_prompt,
                        "filename": filename,
                        "url": f"/api/images/{filename}",
                        "message": f"Watermark-free AI image generated for '{clean_prompt}'.",
                        "gpu": gpu
                    }
        except Exception:
            pass

        # 3. Pollinations AI Standard SDXL Engine
        try:
            encoded = urllib.parse.quote(clean_prompt)
            seed = random.randint(1, 99999999)
            std_url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height + 40}&seed={seed}"
            headers = {"User-Agent": USER_AGENT}
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
                res = await client.get(std_url)
                if res.status_code == 200 and len(res.content) > 2000:
                    filename = ImageService._save_processed_image(res.content, width, height, has_watermark_margin=True)
                    return {
                        "success": True,
                        "mode": "neural_sdxl",
                        "prompt": clean_prompt,
                        "filename": filename,
                        "url": f"/api/images/{filename}",
                        "message": f"Watermark-free high-definition AI image synthesized for '{clean_prompt}'.",
                        "gpu": gpu
                    }
        except Exception:
            pass

        # 4. Wikimedia Photographic Knowledge Search
        wiki_file = await ImageService._fetch_from_wikimedia(clean_prompt, width, height)
        if wiki_file:
            return {
                "success": True,
                "mode": "photographic_search",
                "prompt": clean_prompt,
                "filename": wiki_file,
                "url": f"/api/images/{wiki_file}",
                "message": f"High-resolution photograph retrieved for '{clean_prompt}'.",
                "gpu": gpu
            }

        # 5. Offline Notice (Only if completely without internet)
        notice_file = ImageService.generate_offline_notice(clean_prompt, width=width, height=height)
        return {
            "success": False,
            "mode": "offline_notice",
            "prompt": clean_prompt,
            "filename": notice_file,
            "url": f"/api/images/{notice_file}",
            "message": "Network offline: live image generation requires internet or local ComfyUI.",
            "gpu": gpu
        }

    @staticmethod
    def list_images() -> List[Dict[str, Any]]:
        """List generated images saved in images folder."""
        results = []
        if not settings.IMAGES_PATH.exists():
            return []

        for f in sorted(settings.IMAGES_PATH.glob("*.png"), key=os.path.getmtime, reverse=True):
            if f.name.startswith("jenni_art_"):
                continue  # Skip old geometric placeholder circles
            stat = f.stat()
            results.append({
                "filename": f.name,
                "url": f"/api/images/{f.name}",
                "size_kb": round(stat.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        return results

image_service = ImageService()
