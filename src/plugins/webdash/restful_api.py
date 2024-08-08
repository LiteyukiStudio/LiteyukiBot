from fastapi import FastAPI, APIRouter
from .common import *

device_info_router = APIRouter(prefix="/api/device-info")
bot_info_router = APIRouter(prefix="/api/bot-info")


@device_info_router.get("/")
async def device_info():
    return {
            "message": "Hello Device Info"
    }


@bot_info_router.get("/")
async def bot_info():
    return {
            "message": "Hello Bot Info"
    }


app.include_router(device_info_router)
app.include_router(bot_info_router)
