import asyncio
import cv2
import numpy as np
from aiohttp import web
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from video_utils import process_frame_canvas
from ws_handlers import websocket_handler
from cleanup import cleanup

FRAME_RATE = 1 / 30

async def index(request):
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        html_content = index_path.read_text(encoding="utf-8")
    else:
        html_content = "<html><body><h1>ESP32-CAM Stream</h1><p>index.html not found</p></body></html>"
    return web.Response(text=html_content, content_type="text/html")

async def generate_frames(request, pool: ThreadPoolExecutor):
    shutdown_event = request.app['shutdown_event']
    loop = asyncio.get_event_loop()
    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = dict(request.app['video_frames'])
        # process frame canvas in thread pool
        canvas = await loop.run_in_executor(pool, process_frame_canvas, frame_queues)
        _, jpeg_frame = cv2.imencode('.jpg', canvas)
        yield jpeg_frame.tobytes()
        await asyncio.sleep(FRAME_RATE)

async def video_feed(request):
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache"
        }
    )
    await response.prepare(request)
    pool = request.app['thread_pool']
    async for frame in generate_frames(request, pool):
        await response.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
    return response

async def init_app():
    app = web.Application()
    app['shutdown_event'] = asyncio.Event()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=4)
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()

    # Routes
    app.router.add_get("/", index)
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)

    # Cleanup
    app.on_cleanup.append(cleanup)

    return app
