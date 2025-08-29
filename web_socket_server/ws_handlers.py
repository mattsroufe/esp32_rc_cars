import json
import logging
from aiohttp import WSMsgType, web
from time import time
from collections import deque
from video_utils import calculate_frame_rate

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
        client_ip: {"fps": client_data["fps"], "frame_count": client_data["frame_count"]}
        for client_ip, client_data in request.app['video_frames'].items()
    }
    await ws.send_json(video_info)

async def handle_binary_message(msg: WSMsgType, client_ip: str, request: web.Request, ws: web.WebSocketResponse):
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

async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_ip = request.remote or "unknown"
    logging.info(f"Client connected: {client_ip}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await handle_text_message(msg, request, ws)
            elif msg.type == WSMsgType.BINARY:
                await handle_binary_message(msg, client_ip, request, ws)
            elif msg.type == WSMsgType.ERROR:
                logging.error(f"WebSocket error: {ws.exception()}")
    finally:
        logging.info(f"Client disconnected: {client_ip}")

    return ws
