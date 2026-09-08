# ⚡ SoGoal Link Recorder

A modern, high-performance web-based live stream and football match recorder designed for Linux, built with FastAPI, WebSockets, FFmpeg, yt-dlp, and Playwright.

![Dark Mode Accent](https://img.shields.io/badge/Theme-Dark%20%23c6ff00-black?style=flat-square&color=c6ff00)
![Platform](https://img.shields.io/badge/Platform-Linux-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## 🌟 Key Features

- **⚡ Multi-Stream Concurrent Recording**: Record multiple links, streams, or matches at the same time with independent live controls and timers.
- **🎨 Sleek Dark UI (`#c6ff00` Accent)**: Modern cyberpunk/sports dark-mode aesthetic with real-time HUD metrics (Bitrate, FPS, Elapsed Timer, File Size).
- **📂 SoGoal AI Match Hierarchy**: Automatically organizes video files in the exact hierarchy intended for SoGoal storage:
  ```
  storage/assets/videos/
  └── Season_2026_2027/
      └── Persian_Gulf_Pro_League/
          └── match_id_4/
              └── match_id_4_20260908_121500.mp4
  ```
- **⚙️ Dynamic Presets**:
  - **Seasons**: Persian Gulf Pro League seasons (e.g., `Season_2026_2027`, `Season_2025_2026`, custom `+ New` button).
  - **Competitions**: `Persian_Gulf_Pro_League`, `League_Daste_Yek`, `Hazfi_Cup`, `National`, `National_Young`, custom `+ New` button.
  - **Quality & Bitrates**:
    - `Direct Stream Copy (Lossless / Zero CPU)`: Exact bit-for-bit source stream.
    - `1080p High (6000 kbps)`
    - `720p Standard (3000 kbps)`
    - `480p Low (1500 kbps)`
    - `Audio Only (AAC 192k)`
- **🛡️ Safe & Clean Finalization**: Graceful shutdown on Stop (`q` signal / `SIGINT`) guarantees `.mp4` MOOV atom headers are written without file corruption.
- **📁 Library & Quick Actions**: Built-in explorer to preview recordings, launch default player, open directories in file manager, or delete.
- **🖥️ Desktop Launcher**: Starts with a single click from the Linux Desktop (`SoGoal Recorder`).

---

## 🚀 Getting Started

### 1. Launch with One Click
Double click the **`SoGoal Recorder`** desktop shortcut on your Desktop, or run:

```bash
cd "/home/pc-1/Desktop/recorder code"
./run_recorder.sh
```

The web dashboard opens automatically in your browser at:
`http://localhost:8765`

### 2. Manual Start
```bash
cd "/home/pc-1/Desktop/recorder code"
source .venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8765
```

---

## 📁 Storage Configuration

- **Saved Recordings**: `/home/pc-1/Desktop/video recordings`
- Files can easily be copied or synced to your destination storage (e.g. `D:\SoGoalAI\storage\assets\videos\...`).

---

## 🛠️ Tech Stack

- **Backend**: Python 3, FastAPI, Uvicorn, WebSockets, asyncio
- **Streaming Engines**: FFmpeg, yt-dlp, Playwright (Chromium)
- **Frontend**: Modern Vanilla JS, HTML5, CSS3 Glassmorphism

---

Developed for **SoGoal AI** ⚽
