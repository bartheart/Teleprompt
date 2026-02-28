from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from routes import router as api_router, sio


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# mount the socket io app in the root
app = socketio.ASGIApp(socketio_server=sio, other_asgi_app=app)
