import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path("/home/pc-1/Desktop/video recordings")
PRESETS_FILE = BASE_DIR / "presets.json"

DEFAULT_SEASONS = [
    "Season_2026_2027",
    "Season_2025_2026",
    "Season_2024_2025",
]

DEFAULT_COMPETITIONS = [
    "Persian_Gulf_Pro_League",
    "League_Daste_Yek",
    "Hazfi_Cup",
    "National",
    "National_Young",
]

BITRATE_PRESETS = {
    "copy": {
        "label": "Direct Stream Copy (Lossless / Zero CPU - Recommended)",
        "desc": "Saves original source quality directly without re-encoding",
        "ffmpeg_args": ["-c", "copy"],
        "extension": "mp4",
    },
    "1080p_6000k": {
        "label": "1080p High (6000 kbps)",
        "desc": "Full HD encode, crisp action & high bitrate",
        "ffmpeg_args": ["-vf", "scale=-2:1080", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6000k", "-maxrate", "7000k", "-bufsize", "12000k", "-c:a", "aac", "-b:a", "192k"],
        "extension": "mp4",
    },
    "720p_3000k": {
        "label": "720p Standard (3000 kbps)",
        "desc": "HD 720p encode, balanced file size & quality",
        "ffmpeg_args": ["-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "3000k", "-maxrate", "3500k", "-bufsize", "6000k", "-c:a", "aac", "-b:a", "128k"],
        "extension": "mp4",
    },
    "480p_1500k": {
        "label": "480p Low (1500 kbps)",
        "desc": "SD 480p encode, compact storage",
        "ffmpeg_args": ["-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1500k", "-maxrate", "1800k", "-bufsize", "3000k", "-c:a", "aac", "-b:a", "96k"],
        "extension": "mp4",
    },
    "audio_only": {
        "label": "Audio Only (AAC 192k)",
        "desc": "Extracts commentary / audio track only",
        "ffmpeg_args": ["-vn", "-c:a", "aac", "-b:a", "192k"],
        "extension": "m4a",
    },
}

def load_presets():
    if PRESETS_FILE.exists():
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "seasons": data.get("seasons", DEFAULT_SEASONS),
                    "competitions": data.get("competitions", DEFAULT_COMPETITIONS),
                }
        except Exception:
            pass
    return {
        "seasons": DEFAULT_SEASONS.copy(),
        "competitions": DEFAULT_COMPETITIONS.copy(),
    }

def save_presets(seasons, competitions):
    data = {
        "seasons": list(dict.fromkeys(seasons)),
        "competitions": list(dict.fromkeys(competitions)),
    }
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
