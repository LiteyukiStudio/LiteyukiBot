import asyncio
import aiohttp
from nonebot import logger, on_message, Bot
from nonebot.internal.adapter import Event
from nonebot.plugin import PluginMetadata
from nonebot import get_driver

from .adapter_ctx import Context
from .config import plugin_config, Config, NOTICE, MESSAGE
from .gotify import Message, msg_chan, fetch_msg

__plugin_meta__ = PluginMetadata(
    name="Gotify",
    description="使用Gotify API发送消息",
    usage="后台服务插件，无需用户交互",
)

# on plugin load
driver = get_driver()

async def push_thread():
    async with aiohttp.ClientSession() as session:
        while True:
            msg = await fetch_msg()
            try:
                logger.debug(f"Pushing message: {msg}")
                async with session.post(
                        url=plugin_config.gotify_url + "/message",
                        params={"token": plugin_config.gotify_token},
                        data={
                            "title": msg.title,
                            "message": msg.message,
                            "priority": msg.priority,
                        },
                ) as resp:
                    if resp.status != 200:
                        logger.error(
                            f"Push message to server failed: {await resp.text()}"
                        )
                    else:
                        logger.info(f"Push message to server success: {msg}")
            except Exception as e:
                logger.error(f"Push message to server failed: {e}")

@driver.on_startup
async def start_push_thread():
    asyncio.create_task(push_thread())
    logger.info(
        f"Gotify plugin loaded, server: {plugin_config.gotify_url}, token: {plugin_config.gotify_token}"
    )

if MESSAGE in plugin_config.gotify_includes:
    @on_message().handle()
    async def _(event: Event):
        ctx = Context(
            user_id=event.get_user_id(),
            nickname="",
            message=event.get_plaintext(),
            message_type=event.get_type(),
        )
        ctx.handle(event)

        msg_chan << Message(
            title=plugin_config.gotify_title.format(**ctx.model_dump()),
            message=plugin_config.gotify_message.format(**ctx.model_dump()),
        )

if NOTICE in plugin_config.gotify_includes:
    @driver.on_startup
    async def startup():
        if NOTICE in plugin_config.gotify_includes:
            msg_chan << Message(
                title=plugin_config.gotify_nickname,
                message="Bot started",
                priority=plugin_config.gotify_priority,
            )


    @driver.on_shutdown
    async def shutdown():
        if NOTICE in plugin_config.gotify_includes:
            msg_chan << Message(
                title=plugin_config.gotify_nickname,
                message="Bot stopped",
                priority=plugin_config.gotify_priority,
            )


    @driver.on_bot_connect
    async def bot_connect(bot: Bot):
        if NOTICE in plugin_config.gotify_includes:
            msg_chan << Message(
                title=plugin_config.gotify_nickname,
                message=f"Bot connected: {bot.self_id}",
                priority=plugin_config.gotify_priority,
            )


    @driver.on_bot_disconnect
    async def bot_disconnect(bot: Bot):
        if NOTICE in plugin_config.gotify_includes:
            msg_chan << Message(
                title=plugin_config.gotify_nickname,
                message=f"Bot disconnected: {bot.self_id}",
                priority=plugin_config.gotify_priority,
            )



