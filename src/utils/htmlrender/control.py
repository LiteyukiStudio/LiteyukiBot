import platform
from contextlib import asynccontextmanager
from typing import Optional, AsyncIterator

import pyppeteer
import pyppeteer.browser
import pyppeteer.errors
import pyppeteer.page

from liteyuki.log import logger

# from liteyuki.plugin import PluginMetadata, PluginType
from src.utils.base.config import get_config

# __plugin_meta__ = PluginMetadata(
#     name="页面渲染组件",
#     description="提供跨平台的多用途页面渲染功能，是nontbot-plugin-htmlrender的高级替代",
#     type=PluginType.MODULE,
#     author="金羿Eilles",
#     extra={
#         "license": "汉钰律许可协议 第一版",
#     },
# )

_browser: Optional[pyppeteer.browser.Browser] = None


async def init(**kwargs) -> pyppeteer.browser.Browser:
    global _browser
    logger.info("正在初始化浏览器")

    chromium_path = get_config("chromium_path")

    if chromium_path:
        try:
            _browser = await pyppeteer.launch(executablePath=chromium_path, **kwargs)
        except pyppeteer.errors.PyppeteerError as e:
            logger.error(f"浏览器启动失败：{e}")
            raise

        logger.success("浏览器注册成功")
        return _browser
    else:

        logger.error("请在配置文件中设置 chromium_path")
        raise pyppeteer.errors.BrowserError(
            "未配置浏览器地址；若曾用过nonebot-plugin-htmlrender，则可在 {} 处寻得一可用之chromium".format(
                "%USERPROFILE%\\AppData\\Local\\ms-playwright"
                if platform.system() == "Windows"
                else (
                    "~/Library/Caches/ms-playwright"
                    if platform.system() == "Darwin"
                    else "~/.cache/ms-playwright"
                )
            )
        )


async def get_browser(**kwargs) -> pyppeteer.browser.Browser:
    return (
        _browser
        if _browser and _browser._connection._connected
        else await init(**kwargs)
    )


@asynccontextmanager
async def get_new_page(
    viewport: Optional[dict] = None,
    cookie: Optional[dict] = None,
    useragent: Optional[str] = None,
) -> AsyncIterator[pyppeteer.page.Page]:

    browser = await get_browser()
    page = await browser.newPage()
    # device_scale_factor=device_scale_factor, **kwargs
    if viewport:
        await page.setViewport(viewport)
    if cookie:
        await page.setCookie(cookie)
    if useragent:
        await page.setUserAgent(useragent)

    try:
        yield page
    finally:
        await page.close()


async def shutdown_browser():
    global _browser
    if _browser:
        if _browser._connection._connected:
            await _browser.close()
        _browser = None
