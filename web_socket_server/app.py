import logging
import asyncio
from aiohttp import web
from server import init_app

def main():
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(init_app())

    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    loop.run_until_complete(site.start())
    logging.info("Server started at http://0.0.0.0:8080")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("Ctrl+C received, shutting down...")
    finally:
        loop.run_until_complete(app.shutdown())
        loop.run_until_complete(app.cleanup())
        loop.run_until_complete(runner.cleanup())
        loop.close()

if __name__ == "__main__":
    main()
