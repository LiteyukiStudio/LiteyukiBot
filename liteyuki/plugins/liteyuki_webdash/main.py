from fastapi import FastAPI
from nonebot import get_app
from .restful_api import *

@app.get("/")
async def root():
    return {"message": "Hello World"}
