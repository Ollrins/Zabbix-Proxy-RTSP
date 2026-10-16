#!/usr/bin/env python3
import os
import sys
import re
import time
import argparse
import json
import subprocess
import contextlib
import numpy as np
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

import cv2

LOGFILE = "/var/log/check_rtsp.log"
FFMPEG_LOGFILE = "/var/log/check_rtsp_ffmpeg.log"
MAX_LOG_SIZE_MB = 15


def log(msg):
    try:
        if os.path.exists(LOGFILE) and os.path.getsize(LOGFILE) > MAX_LOG_SIZE_MB * 1024 * 1024:
            with open(LOGFILE, "w") as f:
                f.write(f"[{datetime.now(timezone.utc).isoformat()}] Log rotated due to size\n")
    except Exception:
        pass

    try:
        with open(LOGFILE, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")
    except Exception:
        pass


def mask_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
        return url
    except Exception:
        return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


@contextlib.contextmanager
def suppress_stderr(log_path=FFMPEG_LOGFILE):
    try:
        log_file = open(log_path, "a")
    except Exception:
        log_file = open(os.devnull, "w")

    old_stderr_fd = os.dup(2)
    os.dup2(log_file.fileno(), 2)
    try:
        yield
    finally:
        os.dup2(old_stderr_fd, 2)
        os.close(old_stderr_fd)
        try:
            log_file.close()
        except Exception:
            pass


def parse_args():
    p = argparse.ArgumentParser(description="Hybrid RTSP check via OpenCV + GStreamer + FFprobe")
    p.add_argument("login")
    p.add_argument("password")
    p.add_argument("ip")
    p.add_argument("port")
    p.add_argument("path")
    p.add_argument("--timeout", "-t", type=int, default=5, help="Timeout in seconds")
    return p.parse_args()


def capture_rtsp(cap, duration=3.0):
    start_time = time.time()
    deadline = start_time + duration
    frames = 0
    sizes = []
    brightness = []
    change_levels = []
    prev_gray = None
    width = height = 0

    frame_skip = 3

    while time.time() < deadline:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        frames += 1
        sizes.append(frame.nbytes)
        height, width = frame.shape[:2]

        if frames % frame_skip == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness.append(np.mean(gray))

            if prev_gray is not None:
                delta = np.mean(np.abs(gray.astype("int16") - prev_gray.astype("int16")))
                change_levels.append(delta)

            prev_gray = gray

    cap.release()

    if frames == 0:
        return "no_frames", 0, 0.0, (0, 0), 0.0, 0.0, 0.0, "Connected, but no valid frames"

    avg_kb = round(sum(sizes) / len(sizes) / 1024, 2)
    avg_brightness = round(float(np.mean(brightness)) if brightness else 0.0, 2)
    change_level = round(float(np.mean(change_levels)) if change_levels else 0.0, 2)
    fps = round(frames / duration, 2)

    return "ok", frames, avg_kb, (width, height), avg_brightness, change_level, fps, ""


def try_opencv_backends(url, timeout, use_gstreamer=False):
    backend_name = "OpenCV"
    if use_gstreamer:
        backend_name = "GStreamer"
        url = f'rtspsrc location="{url}" latency=200 ! decodebin ! videoconvert ! appsink'
        cap = cv2.VideoCapture(url, cv2.CAP_GSTREAMER)
    else:
        cap = cv2.VideoCapture(url)

    if not cap.isOpened():
        return "error", 0, 0.0, (0, 0), 0.0, 0.0, 0.0, f"{backend_name} failed to open stream"

    timeout_ms = int(timeout * 1000)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)

    status, frames, avg_kb, res, brightness, change_level, fps, note = capture_rtsp(cap)
    return status, frames, avg_kb, res, brightness, change_level, fps, note


def fallback_ffprobe(url, timeout):
    cmd = [
        "ffprobe", "-v", "error",
        "-rtsp_transport", "tcp",
        "-timeout", str(int(timeout * 1e6)),
        "-i", url,
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name",
        "-of", "json"
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        streams = json.loads(p.stdout).get("streams") or []
        if not streams:
            log("FFprobe fallback: no streams found")
            return None
        info = streams[0]
        return {
            "codec": info.get("codec_name") or "",
            "width": info.get("width") or 0,
            "height": info.get("height") or 0,
        }
    except Exception as e:
        log(f"FFprobe fallback failed: {e}")
        return None


def main():
    args = parse_args()
    base_url = f"rtsp://{args.login}:{args.password}@{args.ip}:{args.port}/{args.path}"
    log(f"Checking: {mask_url(base_url)}")

    with suppress_stderr():
        latency_start = time.time()
        status, frames, avg_kb, res, brightness, change_level, fps, note = \
            try_opencv_backends(base_url, args.timeout)
        latency_ms = int((time.time() - latency_start) * 1000)

        if status == "error":
            log("Trying GStreamer fallback...")
            latency_start = time.time()
            status, frames, avg_kb, res, brightness, change_level, fps, note = \
                try_opencv_backends(base_url, args.timeout, use_gstreamer=True)
            latency_ms = int((time.time() - latency_start) * 1000)

    width_val = res[0] if res else 0
    height_val = res[1] if res else 0
    resolution_pixels = width_val * height_val

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "url": mask_url(base_url),
        "status": status,
        "latency_ms": latency_ms,
        "frames_read": frames,
        "avg_frame_size_kb": avg_kb if avg_kb is not None else 0,
        "width": width_val,
        "height": height_val,
        "resolution_pixels": resolution_pixels,
        "avg_brightness": brightness,
        "frame_change_level": change_level,
        "real_fps": fps,
        "note": note or ""
    }

    if status == "error":
        meta = fallback_ffprobe(base_url, args.timeout)
        if meta:
            result["status"] = "no_frames"
            result["codec"] = meta.get("codec") or ""
            result["width"] = meta.get("width") or 0
            result["height"] = meta.get("height") or 0
            result["resolution_pixels"] = result["width"] * result["height"]
            result["note"] += " | Metadata via ffprobe"

    log(f"Result: {result}")
    print(json.dumps(result))
    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
