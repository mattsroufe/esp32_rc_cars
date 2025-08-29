import asyncio
from aiohttp import web
from server import init_app

async def main():
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    print("Server started at http://0.0.0.0:8080")
    try:
        # Keep running until Ctrl+C
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Ctrl+C received, shutting down...")
    finally:
        await app.shutdown()
        await app.cleanup()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
