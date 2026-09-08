import asyncio
import os
import re
import signal
import sys
import time
import shutil
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import BITRATE_PRESETS, DEFAULT_OUTPUT_DIR


def format_bytes(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    total_sec = int(seconds)
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class RecordingSession:
    id: str
    url: str
    season: str
    competition: str
    match_name: str
    bitrate_preset: str
    capture_type: str  # "auto", "ffmpeg", "ytdlp", "browser"
    output_path: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "starting"  # "starting", "recording", "stopping", "completed", "error"
    error_message: Optional[str] = None
    file_size: int = 0
    fps: str = "--"
    current_bitrate: str = "--"
    speed: str = "1.0x"
    logs: deque = field(default_factory=lambda: deque(maxlen=40))
    process: Optional[asyncio.subprocess.Process] = None
    task: Optional[asyncio.Task] = None

    def to_dict(self) -> dict:
        now = time.time()
        elapsed = (self.end_time or now) - self.start_time if self.start_time else 0
        return {
            "id": self.id,
            "url": self.url,
            "season": self.season,
            "competition": self.competition,
            "match_name": self.match_name,
            "bitrate_preset": self.bitrate_preset,
            "capture_type": self.capture_type,
            "output_path": self.output_path,
            "output_filename": Path(self.output_path).name,
            "start_time": self.start_time,
            "elapsed_seconds": max(0, int(elapsed)),
            "elapsed_formatted": format_duration(elapsed),
            "status": self.status,
            "error_message": self.error_message,
            "file_size_bytes": self.file_size,
            "file_size_formatted": format_bytes(self.file_size),
            "fps": self.fps,
            "current_bitrate": self.current_bitrate,
            "speed": self.speed,
            "logs": list(self.logs)[-15:],
        }


class RecordingManager:
    def __init__(self, output_root: Path = DEFAULT_OUTPUT_DIR):
        self.output_root = output_root
        self.sessions: Dict[str, RecordingSession] = {}

    def get_all_sessions(self) -> List[dict]:
        self._update_metrics()
        return [s.to_dict() for s in self.sessions.values()]

    def get_session(self, session_id: str) -> Optional[RecordingSession]:
        return self.sessions.get(session_id)

    def _update_metrics(self):
        for s in self.sessions.values():
            if os.path.exists(s.output_path):
                try:
                    s.file_size = os.path.getsize(s.output_path)
                except OSError:
                    pass

    def start_recording(
        self,
        session_id: str,
        url: str,
        season: str,
        competition: str,
        match_name: str,
        bitrate_preset: str = "copy",
        capture_type: str = "auto",
    ) -> RecordingSession:
        if session_id in self.sessions and self.sessions[session_id].status in ["starting", "recording"]:
            raise ValueError(f"Recording session {session_id} is already running.")

        # Sanitize folder components
        safe_season = re.sub(r"[^\w\-_.]", "_", season.strip()) or "Season_2026_2027"
        safe_comp = re.sub(r"[^\w\-_.]", "_", competition.strip()) or "Persian_Gulf_Pro_League"
        safe_match = re.sub(r"[^\w\-_.]", "_", match_name.strip()) or f"match_{int(time.time())}"

        # Build folder hierarchy: .../Season_2026_2027/Persian_Gulf_Pro_League/match_id_4/
        target_dir = self.output_root / safe_season / safe_comp / safe_match
        target_dir.mkdir(parents=True, exist_ok=True)

        # Output filename
        preset_info = BITRATE_PRESETS.get(bitrate_preset, BITRATE_PRESETS["copy"])
        ext = preset_info.get("extension", "mp4")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_match}_{timestamp_str}.{ext}"
        output_path = str(target_dir / filename)

        session = RecordingSession(
            id=session_id,
            url=url,
            season=safe_season,
            competition=safe_comp,
            match_name=safe_match,
            bitrate_preset=bitrate_preset,
            capture_type=capture_type,
            output_path=output_path,
        )
        self.sessions[session_id] = session

        # Launch async task
        session.task = asyncio.create_task(self._run_recording(session))
        return session

    async def stop_recording(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        if session.status not in ["recording", "starting"]:
            return

        session.status = "stopping"
        session.logs.append("Finalizing recording stream cleanly...")

        proc = session.process
        if proc and proc.returncode is None:
            try:
                # Try sending 'q' to ffmpeg stdin for graceful finish
                if proc.stdin and not proc.stdin.is_closing():
                    try:
                        proc.stdin.write(b"q\n")
                        await proc.stdin.drain()
                    except Exception:
                        pass
                
                # Also send SIGINT (Ctrl+C equivalent) so container flushes cleanly
                proc.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            except Exception as e:
                session.logs.append(f"Signal exception: {e}")

        # Let the task finish and finalize
        if session.task:
            try:
                await asyncio.wait_for(asyncio.shield(session.task), timeout=10.0)
            except asyncio.TimeoutError:
                if proc and proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                session.status = "completed"
                session.end_time = time.time()

    async def _run_recording(self, session: RecordingSession):
        try:
            url = session.url.strip()
            # Determine actual tool
            is_direct_stream = any(url.lower().endswith(ext) or ext in url.lower() for ext in [".m3u8", ".mpd", ".ts", ".flv", "rtsp://", "rtmp://"])
            is_web_portal = any(d in url.lower() for d in ["youtube.com", "youtu.be", "twitch.tv", "aparat.com", "telewebion.com", "anten.ir", "vimeo.com"])
            
            chosen_engine = session.capture_type
            if chosen_engine == "auto":
                chosen_engine = "ffmpeg" if (is_direct_stream and not is_web_portal) else "ytdlp"
            elif chosen_engine == "ffmpeg" and is_web_portal:
                session.logs.append("Notice: Web portal URL detected. Auto-switching to yt-dlp extractor engine.")
                chosen_engine = "ytdlp"

            session.logs.append(f"Selected engine: {chosen_engine} for URL: {url[:60]}...")

            if chosen_engine == "ffmpeg":
                await self._run_ffmpeg(session, url)
            elif chosen_engine == "ytdlp":
                await self._run_ytdlp(session, url)
            elif chosen_engine == "browser":
                await self._run_browser(session, url)
            else:
                await self._run_ffmpeg(session, url)

        except asyncio.CancelledError:
            session.logs.append("Recording cancelled.")
        except Exception as ex:
            session.status = "error"
            session.error_message = str(ex)
            session.logs.append(f"Error: {ex}")
        finally:
            if session.status != "error":
                session.status = "completed"
            session.end_time = time.time()
            if os.path.exists(session.output_path):
                session.file_size = os.path.getsize(session.output_path)
            session.logs.append(f"Finished. File size: {format_bytes(session.file_size)}")

    async def _run_ffmpeg(self, session: RecordingSession, stream_url: str):
        preset = BITRATE_PRESETS.get(session.bitrate_preset, BITRATE_PRESETS["copy"])
        ffmpeg_args = preset["ffmpeg_args"]

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "info",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-headers", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n",
            "-i", stream_url,
            *ffmpeg_args,
            "-movflags", "+faststart",
            session.output_path,
        ]

        session.logs.append(f"Starting FFmpeg process: {' '.join(cmd[:6])} ...")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        session.process = proc
        session.status = "recording"

        # Regex patterns for parsing ffmpeg stats
        fps_regex = re.compile(r"fps=\s*([\d.]+)")
        bitrate_regex = re.compile(r"bitrate=\s*([\d.]+\s*\w+/s)")
        speed_regex = re.compile(r"speed=\s*([\d.]+x)")

        async def read_stderr():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue

                session.logs.append(text)

                m_fps = fps_regex.search(text)
                if m_fps:
                    session.fps = m_fps.group(1)
                m_br = bitrate_regex.search(text)
                if m_br:
                    session.current_bitrate = m_br.group(1)
                m_spd = speed_regex.search(text)
                if m_spd:
                    session.speed = m_spd.group(1)

        ret = await proc.wait()
        await stderr_task
        if ret != 0 and session.status != "stopping":
            err_msg = session.logs[-1] if session.logs else f"FFmpeg exited with error code {ret}"
            session.status = "error"
            session.error_message = err_msg

    async def _run_ytdlp(self, session: RecordingSession, url: str):
        # yt-dlp recording
        venv_ytdlp = Path(sys.executable).parent / "yt-dlp"
        ytdlp_bin = str(venv_ytdlp) if venv_ytdlp.exists() else (shutil.which("yt-dlp") or "yt-dlp")
        preset = BITRATE_PRESETS.get(session.bitrate_preset, BITRATE_PRESETS["copy"])
        cmd = [
            ytdlp_bin,
            "--no-part",
            "--no-continue",
            "-o", session.output_path,
        ]

        if shutil.which("node"):
            cmd.extend(["--js-runtimes", "node"])

        if session.bitrate_preset == "audio_only":
            cmd.extend(["-x", "--audio-format", "m4a"])
        elif session.bitrate_preset == "1080p_6000k":
            cmd.extend(["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"])
        elif session.bitrate_preset == "720p_3000k":
            cmd.extend(["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best"])
        elif session.bitrate_preset == "480p_1500k":
            cmd.extend(["-f", "bestvideo[height<=480]+bestaudio/best[height<=480]/best"])
        else:
            # copy / best
            cmd.extend(["-f", "bestvideo+bestaudio/best"])

        cmd.append(url)
        session.logs.append(f"Starting yt-dlp ({ytdlp_bin})...")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        session.process = proc
        session.status = "recording"

        async def read_stdout():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    session.logs.append(text)
                    if "%" in text:
                        parts = text.split()
                        for p in parts:
                            if p.endswith("B/s") or p.endswith("b/s"):
                                session.current_bitrate = p

        async def read_stderr():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    session.logs.append(f"[stderr] {text}")

        t1 = asyncio.create_task(read_stdout())
        t2 = asyncio.create_task(read_stderr())
        ret = await proc.wait()
        await asyncio.gather(t1, t2)
        if ret != 0 and session.status != "stopping":
            err_msg = session.logs[-1] if session.logs else f"yt-dlp failed with exit code {ret}"
            session.status = "error"
            session.error_message = err_msg

    async def _run_browser(self, session: RecordingSession, url: str):
        # Browser capture using Playwright or Chromium
        session.logs.append("Launching Headless Chromium for Web Page recording...")
        try:
            from playwright.async_api import async_playwright
            temp_rec_dir = Path(session.output_path).parent / f"temp_{session.id}"
            temp_rec_dir.mkdir(parents=True, exist_ok=True)

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--autoplay-policy=no-user-gesture-required"]
                )
                context = await browser.new_context(
                    record_video_dir=str(temp_rec_dir),
                    record_video_size={"width": 1920, "height": 1080},
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()
                session.logs.append(f"Navigating to {url}...")
                await page.goto(url, wait_until="networkidle", timeout=45000)
                session.status = "recording"
                session.logs.append("Page loaded. Recording video feed...")

                # Loop until session status changes to stopping or completed
                while session.status == "recording":
                    await asyncio.sleep(1.0)
                    session.logs.append("Browser tab recording active...")

                await context.close()
                await browser.close()

                # Find the recorded webm file in temp_rec_dir and remux/rename to output_path
                recorded_files = list(temp_rec_dir.glob("*.webm"))
                if recorded_files:
                    latest = max(recorded_files, key=os.path.getmtime)
                    # Convert to target format using ffmpeg
                    remux_cmd = [
                        "ffmpeg", "-y", "-i", str(latest),
                        "-c:v", "libx264", "-c:a", "aac", session.output_path
                    ]
                    proc_remux = await asyncio.create_subprocess_exec(*remux_cmd)
                    await proc_remux.wait()
                    shutil.rmtree(temp_rec_dir, ignore_errors=True)
                else:
                    session.logs.append("Warning: No video recorded by browser context.")

        except Exception as e:
            session.logs.append(f"Browser capture exception: {e}")
            raise e
