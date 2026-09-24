import asyncio

from fastapi import FastAPI

app = FastAPI()


@app.get("/delay/{ms}")
async def delay(ms: int):
    await asyncio.sleep(ms / 1000)
    return {"delayed_ms": ms}
