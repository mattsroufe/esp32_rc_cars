#!/usr/bin/env python3
"""
Optimized async MJPEG server with CUDA:
- TurboJPEG encode (if available)
- Preallocated / reusable canvas
- Precise frame pacing
- OpenCV CUDA acceleration where available
"""
import os
import asyncio
import logging
import json
import cv2
import numpy as np
from time import time
from collections import deque
from typing import Dict, Deque, Tuple, Any
from multiprocessing import cpu_count
from concurrent.futures import ThreadPoolExecutor
from aiohttp import web, WSMsgType
import contextlib

# -------------------------
# Config (env overrides)
# -------------------------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
FRAME_RATE_FPS = float(os.getenv("FRAME_RATE", "60"))
FRAME_INTERVAL = 1.0 / FRAME_RATE_FPS
MAX_EXPECTED_CLIENTS = int(os.getenv("MAX_EXPECTED_CLIENTS", "8"))
MAX_THREADS = max(2, min(MAX_EXPECTED_CLIENTS * 2, cpu_count() * 2))
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "320"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "240"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))
MAX_FRAMES_PER_CLIENT = int(os.getenv("MAX_FRAMES_PER_CLIENT", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="[%(asctime)s] %(levelname)s: %(message)s")

# -------------------------
# Optional accelerators
# -------------------------
# TurboJPEG
try:
    from turbojpeg import TurboJPEG
    _jpeg = TurboJPEG()
    HAVE_TURBOJPEG = True
    logging.info("TurboJPEG available: will use for final encoding.")
except Exception:
    _jpeg = None
    HAVE_TURBOJPEG = False
    logging.info("TurboJPEG not available: falling back to cv2.imencode().")

# OpenCV CUDA
HAVE_CUDA = False
try:
    if cv2.cuda.getCudaEnabledDeviceCount() > 0:
        HAVE_CUDA = True
        logging.info("OpenCV CUDA available: will use GPU resize/upload where possible.")
except Exception:
    HAVE_CUDA = False
    logging.info("OpenCV CUDA not available.")

# -------------------------
# Type aliases
# -------------------------
FrameQueue = Deque[Tuple[memoryview, float]]
VideoFrames = Dict[str, Dict[str, Any]]  # { ip: { "frames": deque, "fps": float } }

# -------------------------
# Utilities
# -------------------------
def calc_fps(q: FrameQueue) -> float:
    if len(q) < 2:
        return 0.0
    dt = q[-1][1] - q[0][1]
    return round((len(q)-1) / dt, 1) if dt > 0 else 0.0

def calculate_grid_dimensions(n: int) -> Tuple[int, int]:
    if n <= 0:
        return 1, 1
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    return rows, cols

# -------------------------
# Frame composition (runs in threadpool)
# -------------------------
def process_frame_canvas_sync(frame_queues: VideoFrames, canvas_info: Dict[str, Any]) -> bytes:
    """
    Synchronous heavy work: builds the canvas and returns encoded JPEG bytes.
    Uses canvas_info to re-use preallocated buffer and to optionally use CUDA.
    """
    num_clients = len(frame_queues)
    rows, cols = calculate_grid_dimensions(num_clients)

    desired_h = rows * FRAME_HEIGHT
    desired_w = cols * FRAME_WIDTH

    canvas = canvas_info.get("canvas")
    if canvas is None or canvas.shape[0] != desired_h or canvas.shape[1] != desired_w:
        canvas = np.zeros((desired_h, desired_w, 3), dtype=np.uint8)
        canvas_info["canvas"] = canvas
        canvas_info["rows"] = rows
        canvas_info["cols"] = cols
    else:
        canvas.fill(0)

    use_cuda = canvas_info.get("use_cuda", False) and HAVE_CUDA

    for idx, (client_ip, client_data) in enumerate(frame_queues.items()):
        frames = client_data.get("frames")
        if not frames:
            continue
        compressed_mv, _ = frames[-1]
        if compressed_mv is None:
            continue

        arr = np.frombuffer(compressed_mv, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            continue

        # Resize using CUDA if enabled
        if frame.shape[0] != FRAME_HEIGHT or frame.shape[1] != FRAME_WIDTH:
            if use_cuda:
                try:
                    gpu_frame = cv2.cuda_GpuMat()
                    gpu_frame.upload(frame)
                    gpu_resized = cv2.cuda.resize(gpu_frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_LINEAR)
                    frame = gpu_resized.download()
                except Exception:
                    frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
            else:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)

        y = (idx // cols) * FRAME_HEIGHT
        x = (idx % cols) * FRAME_WIDTH

        if use_cuda:
            try:
                gpu_canvas = cv2.cuda_GpuMat()
                gpu_canvas.upload(canvas)
                gpu_canvas_roi = gpu_canvas.rowRange(y, y + FRAME_HEIGHT).colRange(x, x + FRAME_WIDTH)
                gpu_frame_mat = cv2.cuda_GpuMat()
                gpu_frame_mat.upload(frame)
                gpu_frame_mat.copyTo(gpu_canvas_roi)
                canvas = gpu_canvas.download()
            except Exception:
                canvas[y:y+FRAME_HEIGHT, x:x+FRAME_WIDTH] = frame
        else:
            canvas[y:y+FRAME_HEIGHT, x:x+FRAME_WIDTH] = frame

    # JPEG encode
    if HAVE_TURBOJPEG and _jpeg is not None:
        return _jpeg.encode(canvas, quality=JPEG_QUALITY)
    else:
        ok, buf = cv2.imencode('.jpg', canvas, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        return buf.tobytes() if ok else b''

# -------------------------
# WebSocket handlers
# -------------------------
async def handle_text_message(msg: WSMsgType, request: web.Request, ws: web.WebSocketResponse):
    if msg.data == 'close':
        await ws.close()
        return
    try:
        request.app['control_commands'].update(json.loads(msg.data))
    except json.JSONDecodeError:
        logging.warning(f"Invalid JSON from client {request.remote}: {msg.data}")
        return

    video_info = {
        client_ip: {"fps": client_data.get("fps", 0.0), "frame_count": len(client_data.get("frames", ()))}
        for client_ip, client_data in request.app['video_frames'].items()
    }
    await ws.send_json(video_info)

async def handle_binary_message(msg: WSMsgType, client_ip: str, request: web.Request, ws: web.WebSocketResponse):
    mv = memoryview(msg.data)
    fq = request.app['video_frames'].setdefault(client_ip, {'frames': deque(maxlen=MAX_FRAMES_PER_CLIENT), 'fps': 0.0})
    timestamp = time()
    fq['frames'].append((mv, timestamp))
    fq['fps'] = calc_fps(fq['frames'])

    if client_ip in request.app['control_commands']:
        cmd = request.app['control_commands'][client_ip]
        await ws.send_str(f"CONTROL:{cmd[0]}:{cmd[1]}")

async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=20.0, timeout=60.0)
    await ws.prepare(request)
    client_ip = request.remote or "unknown"
    logging.info(f"WS connect: {client_ip}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await handle_text_message(msg, request, ws)
            elif msg.type == WSMsgType.BINARY:
                await handle_binary_message(msg, client_ip, request, ws)
            elif msg.type == WSMsgType.ERROR:
                logging.error(f"WebSocket error from {client_ip}: {ws.exception()}")
    finally:
        request.app['video_frames'].pop(client_ip, None)
        logging.info(f"WS disconnect: {client_ip}")
    return ws

# -------------------------
# MJPEG stream / pacing
# -------------------------
async def generate_frames(request: web.Request):
    shutdown_event = request.app['shutdown_event']
    pool = request.app['thread_pool']
    loop = asyncio.get_event_loop()
    frame_interval = request.app['frame_rate']
    canvas_info = request.app['canvas_info']

    target_time = time()

    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = dict(request.app['video_frames'])

        try:
            jpeg_bytes = await loop.run_in_executor(pool, process_frame_canvas_sync, frame_queues, canvas_info)
            if jpeg_bytes:
                yield jpeg_bytes
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.warning(f"Frame generation error: {e}")

        target_time += frame_interval
        now = time()
        delay = target_time - now
        if delay <= 0:
            if now - target_time > 1.0:
                target_time = now
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(delay)

async def video_feed(request: web.Request):
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
    )
    await response.prepare(request)
    logging.info("Client connected to /video")

    try:
        async for jpeg in generate_frames(request):
            try:
                await response.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                logging.info("Video client disconnected.")
                break
    finally:
        with contextlib.suppress(Exception):
            await response.write_eof()
        logging.info("Closed /video client connection")
    return response

# -------------------------
# Cleanup
# -------------------------
async def cleanup(app: web.Application):
    logging.info("Cleanup: shutting down.")
    app['shutdown_event'].set()
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task():
            t.cancel()
    app['thread_pool'].shutdown(wait=False, cancel_futures=True)
    logging.info("Cleanup complete.")

# -------------------------
# App factory / bootstrap
# -------------------------
async def create_app():
    app = web.Application()
    app['shutdown_event'] = asyncio.Event()
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=MAX_THREADS)
    app['frame_rate'] = FRAME_INTERVAL
    app['canvas_info'] = {"canvas": None, "rows": 0, "cols": 0, "use_cuda": HAVE_CUDA}

    app.router.add_get("/", lambda r: web.FileResponse("./static/index.html"))
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/static", path="./static", name="static")
    app.on_cleanup.append(cleanup)
    return app

async def main():
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    logging.info(f"Server listening at http://{HOST}:{PORT}")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await app.shutdown()
        await app.cleanup()
        await runner.cleanup()

if __name__ == "__main__":
    logging.getLogger().setLevel(LOG_LEVEL)
    asyncio.run(main())

