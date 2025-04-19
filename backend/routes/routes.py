from fastapi import APIRouter
import socketio
import logging
from typing import Any
from time import time 

# Import our new classes
from services.audio_chunk_handler import AudioChunkHandler
from services.audio_format_handler import AudioFormatHandler
from services.audio_transcriber import AudioTranscriber
from services.context_manager import ContextManager
from backend.services.audio_processor_1 import AudioProcessor

# setup logging 
logging.basicConfig(level=logging.DEBUG)  
logger = logging.getLogger(__name__)

# initialize the app router 
router = APIRouter()

# create the socket instance with ASGI support 
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

# create ASGI app 
socket_app = socketio.ASGIApp(
    socketio_server=sio,
    other_asgi_app=router
)


# define the home route 
@router.get('/')
async def Home():
    return "Home route"


# socket io event handlers 
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('connect_response', {'status': 'connected'}, room=sid)

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    audio_processor.shutdown()



# initialize components
chunk_collector = AudioChunkHandler()
format_handler = AudioFormatHandler()
transcriber = AudioTranscriber(model_name='base', num_workers=4)
context_manager = ContextManager(max_context_size=45)   


# initialize AudioProcessor with components 
audio_processor = AudioProcessor(
    chunk_collector, 
    format_handler, 
    transcriber, 
    context_manager,
    on_transcription=lambda text: logger.info(f"Transcription: {text}")
    )


# to get the mime/ audio format from the browser
@sio.event 
async def mime_type(sid, mime_type: str):
    """
    get the mime type of the audio format
    """
    try:
        audio_processor.set_audio_format(mime_type)
        logger.info(f"MIME type set: {audio_processor.current_audio_format.mime_type}")
    except Exception as e:
        logger.error(f"Invalid MIME type: {e}")


# handle the event of sending audio packets 
@sio.event
async def audio_data(sid, audio_chunk: bytes):
    try:
        current_time = time()

        # process the chunk
        audio_processor.process_audio_chunk(audio_chunk, current_time)

        # try processing the collected chunks 
        result = audio_processor.process_collected_chunks()
    
        if result:
            logger.info(f"Processed transcription: {result}")

        # get and log the current context 
        context = audio_processor.get_current_transcript()
        logger.info(f"Current context: {context}")

    except Exception as e:
        logger.error(f"Error processing audio: {e}")


