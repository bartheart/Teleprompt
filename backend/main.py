import logging
import time

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.routes import WHISPER_MODEL_NAME, get_model, router as api_router, sio


fastapi_app = FastAPI()

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(api_router)


@fastapi_app.on_event("startup")
async def preload_whisper_model() -> None:
    logging.getLogger("teleprompt.latency").setLevel(logging.INFO)
    start = time.perf_counter()
    await get_model()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logging.getLogger("teleprompt.startup").info(
        "whisper_model_loaded name=%s load_ms=%.1f",
        WHISPER_MODEL_NAME,
        elapsed_ms,
    )

# mount the socket io app in the root
app = socketio.ASGIApp(socketio_server=sio, other_asgi_app=fastapi_app)
