"""HTTP request handlers for video streaming."""

import asyncio
import logging

import cv2
from aiohttp import web

from video_utils import process_frame_canvas

logger = logging.getLogger(__name__)

# Re-export websocket_handler for backward compatibility
from ws_handlers import websocket_handler


async def index(request: web.Request) -> web.FileResponse:
    """Serve the main HTML page."""
    return web.FileResponse('./static/index.html')


async def generate_frames(request: web.Request):
    """
    Async generator that yields JPEG frames for the MJPEG stream.

    Combines frames from all connected ESP32 clients into a single
    composite image using a grid layout.
    """
    shutdown_event = request.app['shutdown_event']
    loop = asyncio.get_running_loop()
    pool = request.app['thread_pool']
    frame_interval = request.app['frame_rate']

    while not shutdown_event.is_set():
        try:
            # Get current frame queues (thread-safe copy)
            async with request.app['frame_lock']:
                frame_queues = dict(request.app['video_frames'])

            # Process frames in thread pool (CPU-bound operation)
            canvas = await loop.run_in_executor(pool, process_frame_canvas, frame_queues)

            # Encode as JPEG
            _, jpeg_frame = cv2.imencode('.jpg', canvas)
            yield jpeg_frame.tobytes()

            # Rate limiting
            await asyncio.sleep(frame_interval)

        except asyncio.CancelledError:
            logger.debug("Frame generator cancelled")
            break
        except Exception as e:
            logger.exception(f"Error generating frame: {e}")
            await asyncio.sleep(frame_interval)


async def video_feed(request: web.Request) -> web.StreamResponse:
    """
    MJPEG video stream endpoint.

    Streams a multipart response containing JPEG frames from all
    connected ESP32 cameras arranged in a grid.
    """
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )
    await response.prepare(request)

    try:
        async for frame in generate_frames(request):
            await response.write(
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
    except asyncio.CancelledError:
        logger.debug("Video feed cancelled")
    except ConnectionResetError:
        logger.debug("Video feed client disconnected")
    except Exception as e:
        logger.exception(f"Video feed error: {e}")

    return response
