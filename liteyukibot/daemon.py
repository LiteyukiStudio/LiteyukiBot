import asyncio


class Daemon:
    def __init__(self, **config):
        self.config = config
        
    async def _run(self):
        """liteyukibot入口函数
        """
        pass

    def run(self):
        """liteyukibot入口函数
        """
        asyncio.run(self._run())