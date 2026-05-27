import os
import queue
import re
import subprocess
import sys
import threading
from datetime import timedelta
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html") as f:
        return f.read()


class AnalyzeRequest(BaseModel):
    url: str


def fmt_duration(seconds):
    if not seconds:
        return "Unknown"
    return str(timedelta(seconds=int(seconds)))


def fmt_filesize(size):
    if not size:
        return None
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    raw_formats = info.get("formats") or []

    audio_formats = []
    video_formats = []
    seen_video_keys = set()

    # Fixed MP3 transcodes at the top
    audio_formats.append({
        "format_id": "bestaudio/best",
        "label": "320k MP3",
        "ext": "mp3",
        "filesize": None,
        "vcodec": None,
        "acodec": "mp3",
        "type": "audio",
        "abr": 320,
    })
    audio_formats.append({
        "format_id": "bestaudio/best",
        "label": "128k MP3",
        "ext": "mp3",
        "filesize": None,
        "vcodec": None,
        "acodec": "mp3",
        "type": "audio",
        "abr": 128,
    })

    for f in raw_formats:
        ext = f.get("ext", "")
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        fmt_id = f.get("format_id", "")
        height = f.get("height")
        fps = f.get("fps")
        filesize = f.get("filesize") or f.get("filesize_approx")

        # Skip storyboards / mhtml / manifests
        if ext in ("mhtml", "storyboard") or "storyboard" in fmt_id.lower():
            continue
        if ext in ("m3u8", "mpd"):
            continue

        is_video = vcodec != "none" and height is not None

        if is_video:
            fps_val = int(fps) if fps else 0
            label_fps = f"{fps_val}" if fps_val > 30 else ""
            label = f"{height}p{label_fps}" if label_fps else f"{height}p"

            key = (label, ext)
            if key in seen_video_keys:
                continue
            seen_video_keys.add(key)

            video_formats.append({
                "format_id": fmt_id,
                "label": label,
                "ext": ext,
                "filesize": fmt_filesize(filesize),
                "vcodec": vcodec.split(".")[0],
                "acodec": acodec.split(".")[0] if acodec != "none" else None,
                "type": "video",
                "_height": height or 0,
                "_fps": fps_val,
            })

    video_formats.sort(key=lambda x: (x["_height"], x["_fps"]), reverse=True)
    for f in video_formats:
        del f["_height"]
        del f["_fps"]

    return {
        "title": info.get("title", "Unknown"),
        "duration": fmt_duration(info.get("duration")),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key"),
        "formats": audio_formats + video_formats,
    }


@app.get("/download")
async def download(url: str, format_id: str, ext: str, title: str, abr: int = None):
    """
    Stream yt-dlp output directly to the client using a thread + queue pattern.
    yt-dlp is invoked with outtmpl='-' which writes to stdout, which we pipe and
    relay via a StreamingResponse generator — no disk writes at any point.
    """
    q: queue.Queue = queue.Queue(maxsize=64)
    SENTINEL = object()

    if ext == "mp3":
        fmt = "bestaudio/best"
        postproc_args = [
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", str(abr) if abr else "320K",
        ]
    else:
        fmt = f"{format_id}+bestaudio/best[ext={ext}]/{format_id}/best"
        postproc_args = []

    def run():
        try:
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--quiet",
                "--no-warnings",
                "--format", fmt,
                "--output", "-",
                "--no-part",
            ] + postproc_args + [url]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
            try:
                while True:
                    chunk = proc.stdout.read(65536)
                    if not chunk:
                        break
                    q.put(chunk)
                proc.wait()
            finally:
                proc.stdout.close()
        except Exception:
            pass
        finally:
            q.put(SENTINEL)

    def stream():
        t = threading.Thread(target=run, daemon=True)
        t.start()
        while True:
            item = q.get()
            if item is SENTINEL:
                break
            yield item

    safe_title = re.sub(r'[^\w\s\-.]', '', title).strip()[:100] or "video"
    filename = f"{safe_title}.{ext}"
    encoded_filename = quote(filename)

    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename}"; '
            f"filename*=UTF-8''{encoded_filename}"
        ),
        "X-Content-Type-Options": "nosniff",
    }

    return StreamingResponse(
        stream(),
        headers=headers,
        media_type="application/octet-stream",
    )
