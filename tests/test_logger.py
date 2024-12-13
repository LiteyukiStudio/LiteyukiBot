from liteyuki import logger

def test_logger():
    logger.info('Hello, World!')
    logger.debug('Hello, World!')
    logger.warning('Hello, World!')
    logger.error('Hello, World!')
    logger.critical('Hello, World!')
    logger.success("Hello, World!")
