import uvicorn
from fastapi import FastAPI

app = FastAPI()

def get_app() -> FastAPI:
    """获取 FastAPI 实例"""
    return app

@app.get("/")
async def root():
    return {"message": "Hello LiteyukiBot"}


async def run_app(**kwargs):
    """ASGI app 启动函数，在所有插件加载完后任务启动"""
    config = uvicorn.Config(app, **kwargs, log_config=None)
    server = uvicorn.Server(config)
    await server.serve()