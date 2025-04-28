import asyncio

from fastapi import FastAPI
import hypercorn
import hypercorn.run

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello LiteyukiBot"}


async def run_app():
    """liteyukibot入口函数
    """
    hypercorn.run.serve(app, config=hypercorn.Config.from_mapping(
        bind=["localhost:8000"],
        workers=1,
    ))