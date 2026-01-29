"""Cleanup handlers for graceful shutdown."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def cleanup(app):
    """
    Application cleanup handler.

    Called during app.cleanup() phase of shutdown.
    Cancels remaining background tasks and releases resources.
    """
    logger.info("Running cleanup handlers...")

    # Signal shutdown to all components
    if 'shutdown_event' in app:
        app['shutdown_event'].set()

    # Give active handlers time to notice shutdown
    await asyncio.sleep(0.1)

    # Cancel remaining background tasks (excluding current task)
    current_task = asyncio.current_task()
    pending_tasks = [
        task for task in asyncio.all_tasks()
        if task is not current_task and not task.done()
    ]

    if pending_tasks:
        logger.info(f"Cancelling {len(pending_tasks)} pending task(s)...")
        for task in pending_tasks:
            task.cancel()

        # Wait for tasks to complete cancellation
        results = await asyncio.gather(*pending_tasks, return_exceptions=True)

        # Log any unexpected errors (CancelledError is expected)
        for task, result in zip(pending_tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.warning(f"Task {task.get_name()} raised: {result}")

    # Thread pool shutdown is handled in app.py

    logger.info("Cleanup complete")
