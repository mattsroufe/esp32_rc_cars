import logging
import asyncio
import json
from typing import Dict, Deque, Tuple, Any, Generator
from aiohttp import web, WSMessage
import aiohttp
import cv2
import numpy as np
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from time import time
from pathlib import Path

# Constants
FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
FRAME_RATE: float = 1 / 30

# Type Aliases
FrameQueue = Deque[Tuple[bytes, float]]
VideoFrames = Dict[str, Dict[str, Any]]  # {"frames": FrameQueue, "fps": float, "frame_count": int}
ControlCommands = Dict[str, Tuple[float, float]]

# Utility Functions
def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    cols = int(np.ceil(np.sqrt(num_clients)))
    rows = int(np.ceil(num_clients / cols))
    return rows, cols

def get_offsets(index: int, cols: int) -> Tuple[int, int]:
    return (index % cols) * FRAME_WIDTH, (index // cols) * FRAME_HEIGHT

def calculate_frame_rate(frame_queue: FrameQueue) -> float:
    timestamps = [ts for _, ts in frame_queue]
    if len(timestamps) > 1:
        return round((len(timestamps) - 1) / (timestamps[-1] - timestamps[0]), 1)
    return 0.0

def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    num_clients = len(frame_queues)
    if num_clients == 0:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    rows, cols = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows * FRAME_HEIGHT, cols * FRAME_WIDTH, 3), dtype=np.uint8)

    for i, (client_ip, client_data) in enumerate(frame_queues.items()):
        frame_queue = client_data["frames"]
        if not frame_queue:
            continue
        compressed_frame, _ = frame_queue[-1]
        frame_array = np.frombuffer(compressed_frame, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is None:
            continue
        x_offset, y_offset = get_offsets(i, cols)
        canvas[y_offset:y_offset + FRAME_HEIGHT, x_offset:x_offset + FRAME_WIDTH] = frame

    return canvas

# WebSocket Handlers
async def handle_text_message(msg: WSMessage, request: web.Request, ws: web.WebSocketResponse) -> None:
    if msg.data == 'close':
        await ws.close()
        return

    try:
        request.app['control_commands'].update(json.loads(msg.data))
    except json.JSONDecodeError:
        logging.warning(f"Invalid JSON from client {request.remote}: {msg.data}")
        return

    video_info = {
        client_ip: {"fps": client_data["fps"], "frame_count": client_data["frame_count"]}
        for client_ip, client_data in request.app['video_frames'].items()
    }
    await ws.send_json(video_info)

async def handle_binary_message(msg: WSMessage, client_ip: str, request: web.Request, ws: web.WebSocketResponse) -> None:
    frame_queue = request.app['video_frames'].setdefault(
        client_ip, {"frames": deque(maxlen=10), "fps": 0.0, "frame_count": 0}
    )
    timestamp = time()
    frame_queue["frames"].append((msg.data, timestamp))

    fps = calculate_frame_rate(frame_queue["frames"])
    frame_queue["fps"] = fps
    frame_queue["frame_count"] = len(frame_queue["frames"])

    if client_ip in request.app['control_commands']:
        command = request.app['control_commands'][client_ip]
        await ws.send_str(f"CONTROL:{command[0]}:{command[1]}")

# HTTP Handlers
async def index(request: web.Request) -> web.Response:
    return web.Response(
        text="<html><body><h1>ESP32-CAM Stream</h1><img src='/video'></body></html>",
        content_type="text/html"
    )

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            logging.info(f"Received via WS: {msg.data}")
            await ws.send_str(f"Echo: {msg.data}")
        elif msg.type == WSMsgType.ERROR:
            logging.error(f"WebSocket error: {ws.exception()}")

    return ws

def generate_frames(shutdown_event: asyncio.Event):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logging.error("Could not open video device")
        return

    try:
        while not shutdown_event.is_set():
            ret, frame = cap.read()
            if not ret:
                continue
            _, buffer = cv2.imencode('.jpg', frame)
            yield buffer.tobytes()
    finally:
        cap.release()

async def video_feed(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame"
        },
    )
    await response.prepare(request)

    shutdown_event = request.app['shutdown_event']

    for frame in generate_frames(shutdown_event):
        await response.write(
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        await asyncio.sleep(0.05)  # control frame rate

    return response

async def stream_video(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
            'Cache-Control': 'no-cache',
        }
    )
    await response.prepare(request)

    pool: ThreadPoolExecutor = request.app['process_pool']
    async for frame in generate_frames(request, pool):
        await response.write(
            b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
        )
    return response

# Cleanup Function
async def cleanup(app: web.Application) -> None:
    logging.info("Shutting down resources...")

    # Stop video generators
    app['shutdown_event'].set()

    # Cancel background tasks
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()

    # Shutdown executor quickly
    app['thread_pool'].shutdown(wait=False, cancel_futures=True)

    logging.info("Cleanup finished.")


async def init_app() -> web.Application:
    app = web.Application()
    app['shutdown_event'] = asyncio.Event()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=4)

    # Routes
    app.router.add_get("/", index)
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)

    # Cleanup handler
    app.on_cleanup.append(cleanup)

    return app

# Main Function
def main() -> None:
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(init_app())

    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    loop.run_until_complete(site.start())

    logging.info("Server started at http://0.0.0.0:8080")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("Ctrl+C received, shutting down...")
    finally:
        loop.run_until_complete(app.shutdown())
        loop.run_until_complete(app.cleanup())
        loop.run_until_complete(runner.cleanup())
        loop.close()


if __name__ == "__main__":
    main()
