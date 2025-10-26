import os
import cv2
import json
import asyncio
import logging
import numpy as np
from time import time
from collections import deque
from typing import Dict, Deque, Tuple, Any
from multiprocessing import cpu_count
from aiohttp import web, WSMsgType
from concurrent.futures import ThreadPoolExecutor

# ==========================================================
# ----------------------- CONFIG ---------------------------
# ==========================================================

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
FRAME_RATE_FPS = float(os.getenv("FRAME_RATE", "30"))
FRAME_INTERVAL = 1.0 / FRAME_RATE_FPS
MAX_EXPECTED_CLIENTS = int(os.getenv("MAX_EXPECTED_CLIENTS", "8"))
MAX_THREADS = max(2, min(MAX_EXPECTED_CLIENTS, cpu_count() * 2))

FRAME_WIDTH = 320
FRAME_HEIGHT = 240
JPEG_QUALITY = 80
MAX_FRAMES_PER_CLIENT = 10


# ==========================================================
# -------------------- VIDEO UTILITIES ----------------------
# ==========================================================

FrameQueue = Deque[Tuple[memoryview, float]]
VideoFrames = Dict[str, Dict[str, Any]]

def calculate_grid_dimensions(n: int) -> Tuple[int, int]:
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    return rows, cols

def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    num_clients = len(frame_queues)
    if num_clients == 0:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    rows, cols = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows * FRAME_HEIGHT, cols * FRAME_WIDTH, 3), dtype=np.uint8)

    for i, (client_ip, client_data) in enumerate(frame_queues.items()):
        frames = client_data["frames"]
        if not frames:
            continue

        compressed, _ = frames[-1]
        frame_array = np.frombuffer(compressed, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is None:
            continue

        if frame.shape[:2] != (FRAME_HEIGHT, FRAME_WIDTH):
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)

        x = (i % cols) * FRAME_WIDTH
        y = (i // cols) * FRAME_HEIGHT
        canvas[y:y+FRAME_HEIGHT, x:x+FRAME_WIDTH] = frame

    return canvas


# ==========================================================
# ------------------ WEBSOCKET HANDLERS ---------------------
# ==========================================================

def calc_fps(queue: FrameQueue) -> float:
    if len(queue) < 2:
        return 0.0
    dt = queue[-1][1] - queue[0][1]
    return round((len(queue) - 1) / dt, 1) if dt > 0 else 0.0

async def handle_text(msg: str, request: web.Request, ws: web.WebSocketResponse):
    if msg == "close":
        await ws.close()
        return
    try:
        request.app["control_commands"].update(json.loads(msg))
    except json.JSONDecodeError:
        logging.warning(f"Invalid JSON from {request.remote}: {msg}")
        return

    video_info = {
        ip: {"fps": data["fps"], "frames": len(data["frames"])}
        for ip, data in request.app["video_frames"].items()
    }
    await ws.send_json(video_info)

async def handle_binary(data: bytes, ip: str, app: web.Application, ws: web.WebSocketResponse):
    frame_queue = app["video_frames"].setdefault(
        ip, {"frames": deque(maxlen=MAX_FRAMES_PER_CLIENT), "fps": 0.0}
    )
    timestamp = time()
    frame_queue["frames"].append((memoryview(data), timestamp))
    frame_queue["fps"] = calc_fps(frame_queue["frames"])

    cmd = app["control_commands"].get(ip)
    if cmd:
        await ws.send_str(f"CONTROL:{cmd[0]}:{cmd[1]}")

async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)
    ip = request.remote or "unknown"
    app = request.app
    logging.info(f"Client connected: {ip}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await handle_text(msg.data, request, ws)
            elif msg.type == WSMsgType.BINARY:
                await handle_binary(msg.data, ip, app, ws)
            elif msg.type == WSMsgType.ERROR:
                logging.error(f"WebSocket error: {ws.exception()}")
    finally:
        app["video_frames"].pop(ip, None)
        logging.info(f"Client disconnected: {ip}")
    return ws


# ==========================================================
# --------------------- VIDEO STREAM ------------------------
# ==========================================================

async def generate_frames(request):
    shutdown_event = request.app["shutdown_event"]
    pool = request.app["thread_pool"]
    loop = asyncio.get_event_loop()
    frame_rate = request.app["frame_rate"]

    while not shutdown_event.is_set():
        try:
            async with request.app["frame_lock"]:
                frames_copy = dict(request.app["video_frames"])  # shallow copy

            # Heavy CPU work offloaded
            canvas = await loop.run_in_executor(pool, process_frame_canvas, frames_copy)

            ok, jpeg = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue

            yield jpeg.tobytes()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.warning(f"Frame generation error: {e}")
        await asyncio.sleep(frame_rate)

async def video_feed(request):
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache"
        }
    )
    await response.prepare(request)
    logging.info("Client connected to /video")

    try:
        async for frame in generate_frames(request):
            await response.write(
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                frame + b"\r\n"
            )
    except (ConnectionResetError, asyncio.CancelledError, BrokenPipeError):
        logging.info("Video client disconnected.")
    finally:
        with contextlib.suppress(Exception):
            await response.write_eof()
    return response


# ==========================================================
# ----------------------- CLEANUP ---------------------------
# ==========================================================

async def cleanup(app):
    logging.info("Cleaning up...")
    app["shutdown_event"].set()
    app["thread_pool"].shutdown(wait=False, cancel_futures=True)
    await asyncio.sleep(0.05)
    logging.info("Cleanup done.")


# ==========================================================
# -------------------- APP BOOTSTRAP ------------------------
# ==========================================================

async def create_app():
    app = web.Application()
    app["shutdown_event"] = asyncio.Event()
    app["video_frames"] = {}
    app["control_commands"] = {}
    app["frame_lock"] = asyncio.Lock()
    app["thread_pool"] = ThreadPoolExecutor(max_workers=MAX_THREADS)
    app["frame_rate"] = FRAME_INTERVAL

    app.router.add_get("/", lambda r: web.FileResponse("./static/index.html"))
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/static", path="./static")

    app.on_cleanup.append(cleanup)
    return app

async def main():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    logging.info(f"Server started at http://{HOST}:{PORT}")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await app.shutdown()
        await app.cleanup()
        await runner.cleanup()

if __name__ == "__main__":
    import contextlib
    asyncio.run(main())
