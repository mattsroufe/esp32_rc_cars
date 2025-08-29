import os
import asyncio
import cv2
import numpy as np
from aiohttp import web
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path
from video_utils import process_frame_canvas
from ws_handlers import websocket_handler
from cleanup import cleanup

FRAME_RATE = 1 / 30

MAX_EXPECTED_CLIENTS = int(os.getenv("MAX_EXPECTED_CLIENTS", "8"))
MAX_THREADS = max(2, min(MAX_EXPECTED_CLIENTS, cpu_count() * 2))

async def index(request):
    # Serve index.html from the static folder
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        html_content = index_path.read_text(encoding="utf-8")
        return web.Response(text=html_content, content_type="text/html")
    else:
        return web.Response(text="<h1>index.html not found in /static</h1>", content_type="text/html")

async def generate_frames(request):
    shutdown_event = request.app['shutdown_event']
    loop = asyncio.get_event_loop()
    pool: ThreadPoolExecutor = request.app['thread_pool']

    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = dict(request.app['video_frames'])

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
    async for frame in generate_frames(request):
        await response.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
    return response

async def init_app():
    app = web.Application()
    app['shutdown_event'] = asyncio.Event()
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=MAX_THREADS)

    # Routes
    app.router.add_get("/", index)
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)

    # Serve static folder automatically
    static_path = Path(__file__).parent / "static"
    app.router.add_static("/static", path=static_path, name="static")

    # Cleanup
    app.on_cleanup.append(cleanup)

    return app
