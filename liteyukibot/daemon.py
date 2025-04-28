import asyncio
from typing import Type

from pydantic import BaseModel

from .asgi import run_app
from .config import RawConfig, flatten_dict, load_from_dir, merge_dicts
from .log import logger, set_level
from .utils import pretty_format


class Daemon:
    """Liteyuki 的 守护进程
    """
    def __init__(self, **kwargs: RawConfig):
        """Liteyuki Daemon Init
        Args:
            **kwargs: 其他配置项
        """
        # 加载配置项
        self.config: RawConfig = kwargs
        # 获取配置文件目录
        if isinstance(config_dir := kwargs.get("config_dir", None), str):
            self.config = merge_dicts(self.config, load_from_dir(config_dir))
        # 插入扁平化配置
        self.config = merge_dicts(self.config, flatten_dict(self.config))
        
        # 初始化日志
        set_level(self.config.get("log_level", "INFO"))
        
        logger.debug(
            "configs: %s" % pretty_format(self.config, indent=2)
        )
        
    
    async def _run(self):
        """liteyukibot事件循环入口
        """
        # load plugins
        
        # run asgi app
        asyncio.create_task(
            run_app(
            host=self.config.get("host", "127.0.0.1"),
            port=self.config.get("port", 8080),
            )
        )
        # 挂起
        logger.info("Liteyuki Daemon is running...")
        await asyncio.Event().wait()

    def run(self):
        """Daemon入口函数
        """
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.info("Liteyuki Daemon is exiting...")

    def bind_config[T: BaseModel](self, model: Type[T]) -> T:
        """将配置绑定到 Pydantic 模型，推荐使用`pydantic.Field`声明扁平化键字段名

        Args:
            model (Type[T]): Pydantic 模型类

        Returns:
            T: 绑定后的模型实例
        """
        if not issubclass(model, BaseModel):
            raise TypeError("The provided model must be a subclass of BaseModel.")
        return model(**self.config)