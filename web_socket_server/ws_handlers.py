"""WebSocket message handlers for ESP32 clients and browser control."""

import asyncio
import json
import logging
from time import time
from collections import deque
from typing import Optional, List

from aiohttp import WSMsgType, web

from video_utils import calculate_frame_rate

logger = logging.getLogger(__name__)

# Lock for thread-safe frame queue initialization
_frame_queue_lock = asyncio.Lock()


def validate_command(command: Optional[List]) -> Optional[List[int]]:
    """
    Validate and constrain command values.

    Args:
        command: [speed, angle] list from client

    Returns:
        Validated [speed, angle] or None if invalid
    """
    if not isinstance(command, list) or len(command) != 2:
        return None

    try:
        speed = max(-255, min(255, int(command[0])))
        angle = max(0, min(180, int(command[1])))
        return [speed, angle]
    except (ValueError, TypeError):
        return None


async def handle_text_message(
    msg: WSMsgType,
    request: web.Request,
    ws: web.WebSocketResponse
) -> None:
    """
    Handle text messages from browser clients.

    Browser clients send JSON with control commands for each ESP32.
    Server responds with video stats for each connected ESP32.
    """
    if msg.data == 'close':
        await ws.close()
        return

    try:
        commands = json.loads(msg.data)

        # Validate each command before storing
        validated = {}
        for ip, cmd in commands.items():
            valid_cmd = validate_command(cmd)
            if valid_cmd is not None:
                validated[ip] = valid_cmd

        if validated:
            request.app['control_commands'].update(validated)

    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON from browser client: {msg.data[:100]}")
        return

    # Send back video stats for all connected ESP32s
    video_info = {
        client_ip: {
            "fps": client_data["fps"],
            "frame_count": client_data["frame_count"]
        }
        for client_ip, client_data in request.app['video_frames'].items()
    }
    await ws.send_json(video_info)


async def handle_binary_message(
    msg: WSMsgType,
    client_ip: str,
    request: web.Request,
    ws: web.WebSocketResponse
) -> None:
    """
    Handle binary messages (video frames) from ESP32 clients.

    ESP32 clients send JPEG frames as binary data.
    Server queues frames and sends back control commands.
    """
    # Thread-safe frame queue initialization
    async with _frame_queue_lock:
        if client_ip not in request.app['video_frames']:
            request.app['video_frames'][client_ip] = {
                "frames": deque(maxlen=10),
                "fps": 0.0,
                "frame_count": 0
            }
        frame_queue = request.app['video_frames'][client_ip]

    # Add frame with timestamp
    timestamp = time()
    frame_queue["frames"].append((msg.data, timestamp))
    frame_queue["fps"] = calculate_frame_rate(frame_queue["frames"])
    frame_queue["frame_count"] = len(frame_queue["frames"])

    # Send control command if available for this ESP32
    if client_ip in request.app['control_commands']:
        command = request.app['control_commands'][client_ip]
        await ws.send_str(f"CONTROL:{command[0]}:{command[1]}")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """
    Main WebSocket handler.

    Handles both ESP32 clients (binary frames) and browser clients (JSON commands).
    Registers with shutdown manager for graceful disconnection.
    """
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    client_ip = request.remote or "unknown"
    logger.info(f"WebSocket connected: {client_ip}")

    # Register with shutdown manager
    shutdown_manager = request.app.get('shutdown_manager')
    if shutdown_manager:
        shutdown_manager.register_websocket(ws)

    try:
        async for msg in ws:
            # Check for shutdown
            if request.app['shutdown_event'].is_set():
                break

            if msg.type == WSMsgType.TEXT:
                await handle_text_message(msg, request, ws)
            elif msg.type == WSMsgType.BINARY:
                await handle_binary_message(msg, client_ip, request, ws)
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error from {client_ip}: {ws.exception()}")
                break

    except asyncio.CancelledError:
        logger.debug(f"WebSocket handler cancelled: {client_ip}")
    except Exception as e:
        logger.exception(f"WebSocket error from {client_ip}: {e}")
    finally:
        # Unregister from shutdown manager
        if shutdown_manager:
            shutdown_manager.unregister_websocket(ws)

        # Clean up frame queue for this client
        if client_ip in request.app['video_frames']:
            del request.app['video_frames'][client_ip]

        logger.info(f"WebSocket disconnected: {client_ip}")

    return ws
