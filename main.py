from fastapi import FastAPI
import uvicorn

if __name__ == "__main__":
    app = FastAPI()
    uvicorn.run(app, host="0.0.0.0", port=8080)