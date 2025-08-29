import asyncio
from aiohttp import web
from server import index, video_feed, websocket_handler
from cleanup import cleanup
from config import HOST, PORT, MAX_THREADS, FRAME_RATE
from concurrent.futures import ThreadPoolExecutor

async def create_application():
    app = web.Application()
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

    # Cleanup
    app.on_cleanup.append(cleanup)
    return app


async def main():
    app = await create_application()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    print(f"Server started at http://{HOST}:{PORT}")

    try:
        await asyncio.Event().wait()  # Keep server running
    except KeyboardInterrupt:
        print("Ctrl+C received, shutting down...")
    except asyncio.exceptions.CancelledError:
        # Ignore cancellation during shutdown
        pass
    finally:
        await app.shutdown()
        await app.cleanup()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
