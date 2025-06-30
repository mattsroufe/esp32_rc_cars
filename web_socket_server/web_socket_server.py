import logging
import asyncio
import json
import signal
from typing import Dict, Deque, Tuple, Any, Generator, TypedDict
from aiohttp import web, WSCloseCode, WSMessage
import aiohttp
import cv2
import numpy as np
from pathlib import Path
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from time import time

# Constants
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
FRAME_RATE = 1 / 30
MAX_FRAMES_PER_CLIENT = 10

# Type Aliases
FrameQueue = Deque[Tuple[bytes, float]]

class ClientData(TypedDict):
    frames: FrameQueue
    fps: float
    frame_count: int

VideoFrames = Dict[str, ClientData]
ControlCommands = Dict[str, Tuple[float, float]]

# Utility Functions
def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    cols = int(np.ceil(np.sqrt(num_clients)))
    rows = int(np.ceil(num_clients / cols))
    return rows, cols

def get_offsets(index: int, cols: int) -> Tuple[int, int]:
    x_offset = (index % cols) * FRAME_WIDTH
    y_offset = (index // cols) * FRAME_HEIGHT
    return x_offset, y_offset

def calculate_frame_rate(frame_queue: FrameQueue) -> float:
    timestamps = [ts for _, ts in frame_queue]
    if len(timestamps) > 1:
        return round((len(timestamps) - 1) / (timestamps[-1] - timestamps[0]), 1)
    return 0.0

def encode_frame_to_jpeg(frame: np.ndarray) -> bytes:
    success, encoded = cv2.imencode('.jpg', frame)
    if not success:
        raise ValueError("Failed to encode frame")
    return encoded.tobytes()

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
        if frame is None or frame.shape[:2] != (FRAME_HEIGHT, FRAME_WIDTH):
            continue

        x_offset, y_offset = get_offsets(i, cols)
        canvas[y_offset:y_offset + FRAME_HEIGHT, x_offset:x_offset + FRAME_WIDTH] = frame

    return canvas

# WebSocket Handlers
async def handle_text_message(msg: WSMessage, request: web.Request, ws: web.WebSocketResponse) -> None:
    try:
        data = json.loads(msg.data)
    except json.JSONDecodeError:
        logging.warning("Invalid JSON received")
        return

    if msg.data == 'close':
        await ws.close()
    else:
        request.app['control_commands'].update(data)
        video_info = {
            client_ip: {
                "fps": client_data["fps"],
                "frame_count": client_data["frame_count"]
            }
            for client_ip, client_data in request.app['video_frames'].items()
        }
        await ws.send_json(video_info)

async def handle_binary_message(msg: WSMessage, client_ip: str, request: web.Request, ws: web.WebSocketResponse) -> None:
    frame_queue = request.app['video_frames'].setdefault(
        client_ip, {"frames": deque(maxlen=MAX_FRAMES_PER_CLIENT), "fps": 0.0, "frame_count": 0}
    )

    timestamp = time()
    frame_queue["frames"].append((msg.data, timestamp))
    frame_queue["fps"] = calculate_frame_rate(frame_queue["frames"])
    frame_queue["frame_count"] = len(frame_queue["frames"])

    logging.debug(f"[{client_ip}] Frame received: count={frame_queue['frame_count']}, fps={frame_queue['fps']}")

    if client_ip in request.app['control_commands']:
        command = request.app['control_commands'][client_ip]
        logging.debug(f"[{client_ip}] Sending control command: {command}")
        await ws.send_str(f"CONTROL:{command[0]}:{command[1]}")

# HTTP Handlers
async def index(request: web.Request) -> web.Response:
    try:
        html = Path('index.html').read_text()
        return web.Response(text=html, content_type='text/html')
    except FileNotFoundError:
        logging.error("index.html not found")
        return web.Response(status=404, text="Index file not found.")

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_ip = request.remote or "unknown"
    logging.info(f"Client connected: {client_ip}")

    shutdown_event: asyncio.Event = request.app['shutdown_event']

    try:
        while not ws.closed and not shutdown_event.is_set():
            try:
                msg = await ws.receive(timeout=1.0) # timeout to check for shutdown
            except asyncio.TimeoutError:
                continue # Just wait again, not an error
            if msg.type == aiohttp.WSMsgType.TEXT:
                await handle_text_message(msg, request, ws)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await handle_binary_message(msg, client_ip, request, ws)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logging.error(f"WebSocket error from {client_ip}: {ws.exception()}")
    except asyncio.TimeoutError:
        pass # Loop back and check again
    except Exception as e:
        logging.error(f"Websocket failure: {e}")
    finally:
        logging.info(f"Client disconnected: {client_ip}")
        await ws.close()
    return ws

async def generate_frames(request: web.Request, pool: ProcessPoolExecutor) -> Generator[bytes, None, None]:
    shutdown_event: asyncio.Event = request.app['shutdown_event']
    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = request.app['video_frames']

        try:
            canvas = await asyncio.to_thread(process_frame_canvas, frame_queues)
            jpeg_frame = await asyncio.to_thread(encode_frame_to_jpeg, canvas)
            yield jpeg_frame
        except Exception as e:
            logging.error(f"Frame generation error: {e}")
        await asyncio.sleep(FRAME_RATE)

async def stream_video(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
            'Cache-Control': 'no-cache',
        }
    )
    await response.prepare(request)

    pool: ProcessPoolExecutor = request.app['process_pool']
    shutdown_event: asyncio.Event = request.app['shutdown_event']

    try:
        async for frame in generate_frames(request, pool):
            if shutdown_event.is_set():
                break # stop sending frames when shutting down
            await response.write(
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            )
    except (asyncio.CancelledError, ConnectionResetError, RuntimeError) as e:
        logging.info(f"Stream closed by client: {e}")
    except Exception as e:
        logging.info(f"Unexpected stream error: {e}")
    finally:
        try:
            await response.write_eof()
        except ConnectionResetError:
            pass # Browser already gone
        logging.info("Video stream closed")
    return response

# Graceful Shutdown
async def cleanup(app: web.Application) -> None:
    logging.info("Shutting down thread pool and event loop...")
    app['shutdown_event'].set()
    app['process_pool'].shutdown()

async def shutdown(app: web.Application):
    logging.info("Signal received: shutting down...")
    await cleanup(app)
    await app.shutdown()
    await app.cleanup()

async def setup_signal_handlers(app: web.Application):
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(app)))

# App Factory
def create_app() -> web.Application:
    app = web.Application()

    app['video_frames']: VideoFrames = {}
    app['control_commands']: ControlCommands = {}
    app['frame_lock'] = asyncio.Lock()
    app['shutdown_event'] = asyncio.Event()
    app['process_pool'] = ProcessPoolExecutor(max_workers=4)

    app.router.add_get('/', index)
    app.router.add_get('/video', stream_video)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/static', path='./static', name='static')

    app.on_shutdown.append(cleanup)
    return app

# Main Function
def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
