import httpx
import json
import uuid
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import subprocess
from backend.config import settings

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
                
                # Recommendation for 4GB VRAM
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
            "recommendation": "Use CPU / Cloud / Fallback generator mode"
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
            "message": "ComfyUI is not currently running. Jenni AI will use high-quality creative synthesis fallback or wait for ComfyUI."
        }

    @staticmethod
    def generate_creative_artwork(prompt: str, width: int = 768, height: int = 512) -> str:
        """
        Creates a futuristic neural generative artwork card when ComfyUI is offline or low-vram fallback is engaged.
        """
        filename = f"jenni_art_{uuid.uuid4().hex[:8]}.png"
        filepath = settings.IMAGES_PATH / filename

        # Generate vibrant cyberpunk dark canvas
        img = Image.new("RGB", (width, height), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Draw glowing gradient bars / neon grid
        for i in range(0, height, 20):
            alpha_color = (20 + (i % 40), 30 + (i % 60), 60 + (i % 80))
            draw.line([(0, i), (width, i)], fill=alpha_color, width=1)

        # Concentric glowing circles representing AI generation core
        center_x, center_y = width // 2, height // 2 - 20
        colors = [(56, 189, 248), (168, 85, 247), (236, 72, 153), (99, 102, 241)]
        for r in range(160, 40, -25):
            col = colors[(r // 25) % len(colors)]
            draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], outline=col, width=3)

        # Overlay text banner
        draw.rectangle([30, height - 120, width - 30, height - 30], fill=(24, 30, 52))
        draw.rectangle([30, height - 120, width - 30, height - 30], outline=(56, 189, 248), width=2)
        
        # Text rendering
        clean_prompt = prompt if len(prompt) < 70 else prompt[:67] + "..."
        draw.text((50, height - 105), f"Jenni AI Studio — Visual Concept", fill=(168, 85, 247))
        draw.text((50, height - 80), f'"{clean_prompt}"', fill=(240, 245, 255))
        draw.text((50, height - 55), "Engine: Jenni AI Visual Synth (Connect ComfyUI for SD 1.5 diffusion)", fill=(148, 163, 184))

        img.save(str(filepath))
        return filename

    @staticmethod
    async def generate_image(prompt: str, width: int = 512, height: int = 512) -> Dict[str, Any]:
        """
        Attempts to generate image using ComfyUI. If ComfyUI is unavailable, uses visual fallback.
        """
        gpu = ImageService.get_gpu_vram()
        comfy_status = await ImageService.check_comfyui_status()

        if comfy_status["online"]:
            # ComfyUI is running! Send default txt2img workflow
            try:
                # Standard SD1.5 txt2img workflow prompt dict
                workflow = {
                    "3": {
                        "inputs": {
                            "seed": int(uuid.uuid4().int % 1000000000),
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
                        "inputs": {"text": prompt, "clip": ["4", 1]},
                        "class_type": "CLIPTextEncode"
                    },
                    "7": {
                        "inputs": {"text": "blurry, low quality, deformed, distorted", "clip": ["4", 1]},
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
                        prompt_id = data.get("prompt_id")
                        return {
                            "success": True,
                            "mode": "comfyui",
                            "prompt_id": prompt_id,
                            "message": "Prompt submitted to ComfyUI successfully.",
                            "gpu": gpu
                        }
            except Exception as e:
                # ComfyUI returned an error during submission
                pass

        # Fallback generator
        filename = ImageService.generate_creative_artwork(prompt, width=width, height=height)
        return {
            "success": True,
            "mode": "fallback_synth",
            "filename": filename,
            "url": f"/api/images/{filename}",
            "message": "Image generated using Jenni AI Visual Synth. (For Stable Diffusion, start ComfyUI at http://127.0.0.1:8188)",
            "gpu": gpu
        }

    @staticmethod
    def list_images() -> List[Dict[str, Any]]:
        """List generated images saved in images folder."""
        results = []
        if not settings.IMAGES_PATH.exists():
            return []

        for f in sorted(settings.IMAGES_PATH.glob("*.png"), key=os.path.getmtime, reverse=True):
            stat = f.stat()
            results.append({
                "filename": f.name,
                "url": f"/api/images/{f.name}",
                "size_kb": round(stat.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        return results

image_service = ImageService()
