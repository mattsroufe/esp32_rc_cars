import logging
import asyncio
import json
from typing import Dict, Deque, Tuple, Any, Optional
from aiohttp import web, WSMessage
import aiohttp
import cv2
import numpy as np
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from time import time

# Constants
FRAME_WIDTH, FRAME_HEIGHT = 320, 240
FRAME_RATE = 1 / 30
MAX_FRAMES = 10

# Type Aliases
FrameQueue = Deque[Tuple[bytes, float]]
VideoFrames = Dict[str, Dict[str, Any]]

# Utility Functions
def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    """Calculate the grid layout dimensions based on the number of clients."""
    cols = int(np.ceil(np.sqrt(num_clients)))
    return (cols, (num_clients + cols - 1) // cols)

def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    """Create a canvas with video frames arranged in a grid."""
    num_clients = len(frame_queues)
    if not num_clients:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    cols, rows = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows * FRAME_HEIGHT, cols * FRAME_WIDTH, 3), dtype=np.uint8)

    for i, (client_ip, client_data) in enumerate(frame_queues.items()):
        frame_queue = client_data["frames"]
        if not frame_queue:
            continue

        frame = cv2.imdecode(np.frombuffer(frame_queue[-1][0], dtype=np.uint8), cv2.IMREAD_COLOR)
        x_offset, y_offset = (i % cols) * FRAME_WIDTH, (i // cols) * FRAME_HEIGHT
        canvas[y_offset:y_offset + FRAME_HEIGHT, x_offset:x_offset + FRAME_WIDTH] = frame

    return canvas

async def handle_websocket(ws: web.WebSocketResponse, request: web.Request, client_ip: str):
    """Handle WebSocket connections for messages and frames."""
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            request.app['control_commands'].update(json.loads(msg.data))
            video_info = {
                ip: {"fps": client_data["fps"], "frame_count": len(client_data["frames"])}
                for ip, client_data in request.app['video_frames'].items()
            }
            await ws.send_json(video_info)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            frame_queue = request.app['video_frames'].setdefault(client_ip, {"frames": deque(maxlen=MAX_FRAMES), "fps": 0.0})
            frame_queue["frames"].append((msg.data, time()))
            frame_queue["fps"] = round(len(frame_queue["frames"]) / (frame_queue["frames"][-1][1] - frame_queue["frames"][0][1]), 1) if len(frame_queue["frames"]) > 1 else 0.0
        elif msg.type == aiohttp.WSMsgType.ERROR:
            logging.error(f"WebSocket error: {ws.exception()}")

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await handle_websocket(ws, request, request.remote or "unknown")
    return ws

async def generate_frames(request: web.Request, pool: ProcessPoolExecutor):
    """Generate video frames for streaming."""
    shutdown_event = request.app['shutdown_event']
    while not shutdown_event.is_set():
        canvas = await asyncio.get_running_loop().run_in_executor(pool, process_frame_canvas, request.app['video_frames'])
        _, jpeg_frame = cv2.imencode('.jpg', canvas)
        yield jpeg_frame.tobytes()
        await asyncio.sleep(FRAME_RATE)

async def stream_video(request: web.Request) -> web.StreamResponse:
    """Stream video frames as an HTTP response."""
    response = web.StreamResponse(status=200, headers={'Content-Type': 'multipart/x-mixed-replace; boundary=frame', 'Cache-Control': 'no-cache'})
    await response.prepare(request)
    
    pool = request.app['process_pool']
    async for frame in generate_frames(request, pool):
        await response.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    
    return response

async def cleanup(app: web.Application):
    """Clean up resources on shutdown."""
    app['shutdown_event'].set()
    app['process_pool'].shutdown()

def main():
    logging.basicConfig(level=logging.DEBUG)
    app = web.Application()

    # Shared state
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['shutdown_event'] = asyncio.Event()
    app['process_pool'] = ProcessPoolExecutor(max_workers=4)

    # Routes
    app.router.add_get('/', lambda _: web.FileResponse('index.html'))
    app.router.add_get('/video', stream_video)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/static', path='./static', name='static')

    # Cleanup on shutdown
    app.on_shutdown.append(cleanup)

    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
