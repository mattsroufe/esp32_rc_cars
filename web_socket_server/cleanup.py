import logging

async def cleanup(app):
    logging.info("Running cleanup...")

    # Shutdown thread pool if it exists
    pool = app.get('thread_pool')
    if pool:
        logging.info("Shutting down thread pool...")
        pool.shutdown(wait=False)

    # You can also release other resources here:
    # - Close camera devices
    # - Flush any buffers
    # - Save state if needed

    logging.info("Cleanup complete.")
