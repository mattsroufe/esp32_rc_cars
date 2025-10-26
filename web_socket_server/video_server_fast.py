#!/usr/bin/env python3
"""
Optimized async MJPEG server:
- TurboJPEG encode (if available)
- Preallocated / reusable canvas
- Precise frame pacing
- Optional OpenCV CUDA acceleration (if available)
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
    from turbojpeg import TurboJPEG, TJFLAG_FASTDCT
    _jpeg = TurboJPEG()
    HAVE_TURBOJPEG = True
    logging.info("TurboJPEG available: will use for final encoding.")
except Exception:
    _jpeg = None
    HAVE_TURBOJPEG = False
    logging.info("TurboJPEG not available: falling back to cv2.imencode(). (pip install turbojpeg)")

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
    This is executed via run_in_executor in a worker thread.
    Uses canvas_info to re-use preallocated buffer and to optionally use CUDA.
    """
    num_clients = len(frame_queues)
    rows, cols = calculate_grid_dimensions(num_clients)

    # Ensure canvas shape as required
    desired_h = rows * FRAME_HEIGHT
    desired_w = cols * FRAME_WIDTH

    canvas = canvas_info.get("canvas")
    canvas_shape = canvas.shape if canvas is not None else None
    if canvas is None or canvas_shape[0] != desired_h or canvas_shape[1] != desired_w:
        # allocate or reallocate
        canvas = np.zeros((desired_h, desired_w, 3), dtype=np.uint8)
        canvas_info["canvas"] = canvas
        canvas_info["rows"] = rows
        canvas_info["cols"] = cols
    else:
        canvas.fill(0)

    # If CUDA path is enabled, we'll use cv2.cuda functions per-frame where useful.
    use_cuda = canvas_info.get("use_cuda", False) and HAVE_CUDA

    # Compose frames into canvas
    # iterate in deterministic order (items) to keep layout stable
    for idx, (client_ip, client_data) in enumerate(frame_queues.items()):
        frames = client_data.get("frames")
        if not frames:
            continue
        compressed_mv, _ = frames[-1]
        if compressed_mv is None:
            continue

        # decode (CPU): decode from JPEG bytes -> BGR image
        # If client can send raw frames, you should change this path to avoid decode here.
        arr = np.frombuffer(compressed_mv, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            continue

        # Resize if needed -- use CUDA if available and enabled
        if frame.shape[0] != FRAME_HEIGHT or frame.shape[1] != FRAME_WIDTH:
            if use_cuda:
                try:
                    gpu_frame = cv2.cuda_GpuMat()
                    gpu_frame.upload(frame)
                    gpu_resized = cv2.cuda.resize(gpu_frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_LINEAR)
                    frame = gpu_resized.download()
                except Exception:
                    # fallback to CPU resize
                    frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
            else:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)

        y = (idx // cols) * FRAME_HEIGHT
        x = (idx % cols) * FRAME_WIDTH
        canvas[y:y+FRAME_HEIGHT, x:x+FRAME_WIDTH] = frame

    # JPEG encode final canvas: prefer TurboJPEG if available
    if HAVE_TURBOJPEG and _jpeg is not None:
        # TurboJPEG expects RGB or BGR depending on build — pass BGR raw and set force_gray=False
        # encode returns bytes
        jpeg_bytes = _jpeg.encode(canvas, quality=JPEG_QUALITY)
        return jpeg_bytes
    else:
        # Fall back to cv2.imencode (returns (ok, buf))
        ok, buf = cv2.imencode('.jpg', canvas, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            return b''
        return buf.tobytes()

# -------------------------
# Websocket handlers
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
    # store memoryview to avoid copy
    mv = memoryview(msg.data)
    fq = request.app['video_frames'].setdefault(client_ip, {'frames': deque(maxlen=MAX_FRAMES_PER_CLIENT), 'fps': 0.0})
    timestamp = time()
    fq['frames'].append((mv, timestamp))
    fq['fps'] = calc_fps(fq['frames'])

    # Control command feedback if exists
    if client_ip in request.app['control_commands']:
        cmd = request.app['control_commands'][client_ip]
        # format: CONTROL:cmd0:cmd1 (you may customize)
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
    """Async generator yielding JPEG bytes. Uses precise pacing (target_time)."""
    shutdown_event = request.app['shutdown_event']
    pool = request.app['thread_pool']
    loop = asyncio.get_event_loop()
    frame_interval = request.app['frame_rate']
    canvas_info = request.app['canvas_info']

    # start target time
    target_time = time()

    while not shutdown_event.is_set():
        start = time()
        # snapshot frames briefly under lock to reduce contention
        async with request.app['frame_lock']:
            frame_queues = dict(request.app['video_frames'])  # shallow copy of references (deque objects)

        # Run composition+encode in executor
        try:
            jpeg_bytes = await loop.run_in_executor(pool, process_frame_canvas_sync, frame_queues, canvas_info)
            if jpeg_bytes:
                yield jpeg_bytes
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.warning(f"Frame generation error: {e}")

        # precise pacing: increment target_time and sleep to match interval
        target_time += frame_interval
        now = time()
        delay = target_time - now
        if delay <= 0:
            # We're behind. Don't sleep; but advance target_time to avoid spiraling
            # If we are very far behind, snap target_time to now
            if now - target_time > 1.0:
                target_time = now
            await asyncio.sleep(0)  # yield to event loop
        else:
            await asyncio.sleep(delay)

# MJPEG endpoint
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
    # cancel other tasks
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task():
            t.cancel()
    # shutdown pool
    app['thread_pool'].shutdown(wait=False, cancel_futures=True)
    logging.info("Cleanup complete.")

# -------------------------
# App factory / bootstrap
# -------------------------
import contextlib
from types import SimpleNamespace

async def create_app():
    app = web.Application()
    app['shutdown_event'] = asyncio.Event()
    app['video_frames'] = {}  # ip -> {frames: deque(...), fps: float}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=MAX_THREADS)
    app['frame_rate'] = FRAME_INTERVAL

    # canvas info stores the reusable canvas and flags
    app['canvas_info'] = {"canvas": None, "rows": 0, "cols": 0, "use_cuda": HAVE_CUDA}

    # routes
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
