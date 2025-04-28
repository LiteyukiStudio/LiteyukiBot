from liteyukibot import log, logger


def test_set_level():
    logger.info("Testing logger level")
    logger.debug("Debug message")
    log.set_level("DEBUG")
    logger.debug("Debug message after level change")
    
if __name__ == "__main__":
    test_set_level()
    print("测试完成，你应该只会看到一次debug信息")