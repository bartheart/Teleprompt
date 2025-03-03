from multiprocessing import Queue, MPqueue
from queue import Queue, Empty, Full
from dataclasses import dataclass

# import service classes 
from services.audio_chunk_handler import AudioChunkHandler
from services.audio_dispatcher import AudioDispatcher
from services.queue_service import QueueService
from services.context_manager import ContextManager
from services.audio_format_handler import AudioFormatHandler
from services.audio_transcriber import AudioTranscriber

@dataclass
class Process_Config:
    raw_queue_size: int = 40
    process_queue_size: int = 20
    min_chunks_to_process: int = 10

class AudioChunkHandler:
    """
    handle audio chunks
    """
    def __init__ (self, config: Process_Config):
        # initialize the queue service
        self.queue_service = QueueService(max_size= config.raw_queue_size)

        # intialize components
        self.dispatcher = AudioDispatcher(self.queue_service)
        