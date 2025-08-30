import asyncio
import logging
from aiohttp import web
from server import index, video_feed, websocket_handler
from cleanup import cleanup
from config import HOST, PORT, MAX_THREADS, FRAME_RATE
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)


async def on_shutdown(app: web.Application):
    logging.info("Shutting down, closing WebSockets...")
    for ws in set(app['websockets']):  # copy to avoid modifying while iterating
        try:
            await ws.close(code=1001, message="Server shutdown")
        except Exception as e:
            logging.error(f"Error closing websocket: {e}")


async def create_application():
    app = web.Application()

    # Shared state
    app['websockets'] = set()
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=MAX_THREADS)
    app['frame_rate'] = FRAME_RATE

    # Routes
    app.router.add_get("/", index)
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)

    # Static files
    app.router.add_static("/static", path="./static", name="static")

    # Lifecycle
    app.on_shutdown.append(on_shutdown)
    app.on_cleanup.append(cleanup)

    return app


def main():
    app = asyncio.run(create_application())
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
