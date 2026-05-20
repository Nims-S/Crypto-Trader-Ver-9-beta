from __future__ import annotations

import asyncio

from ver9.observability.logging import get_logger
from ver9.runtime.kernel.runtime_kernel import RuntimeKernel


async def main() -> None:
    logger = get_logger("run_kernel")
    await logger.start()

    kernel = RuntimeKernel(logger=logger)
    shutdown_required = False

    try:
        logger.info("local runtime launch requested")
        await kernel.bootstrap("config.json")
        shutdown_required = True
        logger.info("local runtime bootstrap completed")

        for _ in range(2):
            await asyncio.sleep(1)

        logger.info("local runtime simulation window completed")

    except asyncio.CancelledError:
        logger.warning("local runtime cancellation requested")
        raise

    except KeyboardInterrupt:
        logger.warning("local runtime keyboard interruption requested")

    finally:
        if shutdown_required:
            await kernel.shutdown()
        else:
            await logger.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
