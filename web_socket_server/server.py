import asyncio
import cv2
import numpy as np
from aiohttp import web
from ws_handlers import websocket_handler
from video_utils import process_frame_canvas
from cleanup import cleanup


async def generate_frames(request):
    """Yield a composited canvas of all connected WebSocket video streams."""
    while True:
        async with request.app['frame_lock']:
            frame_queues = dict(request.app['video_frames'])  # copy to avoid race

        loop = asyncio.get_event_loop()
        pool = request.app['thread_pool']
        # Offload canvas processing to thread pool
        canvas = await loop.run_in_executor(pool, process_frame_canvas, frame_queues)

        _, jpeg_frame = cv2.imencode('.jpg', canvas)
        yield jpeg_frame.tobytes()
        await asyncio.sleep(request.app['frame_rate'])


async def video_feed(request):
    """Stream combined frames from all WS clients as MJPEG."""
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache"
        }
    )
    await response.prepare(request)

    try:
        async for frame in generate_frames(request):
            await response.write(
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
    except (asyncio.CancelledError, ConnectionResetError):
        # Client disconnected
        pass
    finally:
        await response.write_eof()

    return response


async def on_shutdown(app: web.Application):
    """Close all open WebSockets gracefully."""
    for ws in set(app['websockets']):
        try:
            await ws.close(code=1001, message="Server shutdown")
        except Exception:
            pass


def create_app():
    """Create the aiohttp application with WebSocket and video feed routes."""
    from concurrent.futures import ThreadPoolExecutor
    import os

    app = web.Application()
    app['websockets'] = set()
    app['video_frames'] = {}  # client_ip -> {"frames": deque, "fps": float, "frame_count": int}
    app['control_commands'] = {}  # client_ip -> (x, y)
    app['frame_lock'] = asyncio.Lock()
    app['frame_rate'] = float(os.environ.get("FRAME_RATE", 1 / 30))
    app['thread_pool'] = ThreadPoolExecutor(max_workers=int(os.environ.get("MAX_THREADS", 4)))

    # Routes
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/video", video_feed)
    app.router.add_static("/", path="static", name="static")

    # Lifecycle
    app.on_shutdown.append(on_shutdown)
    app.on_cleanup.append(cleanup)

    return app
