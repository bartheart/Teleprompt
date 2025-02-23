from queue import Queue, Full, Empty
from dataclasses import dataclass
import logging


class QueueFullError(Exception):
    pass

class QueueEmptyError(Exception):
    pass

@dataclass
class AudioChunk:
    """
    define a data structure for the audio chunk
    """
    sequence_number: int
    audio_data: bytes
    timestamp: float
    # maybe add a header and metadata later

class QueueService:
    """
    handle the queue of audio chunks
    """

    def __init__ (self, max_size:int = 40):
        self.queue = Queue(maxsize= max_size)
        self.logger = logging.getLogger(__name__)

    async def add_chunk_to_queue (self, sequence_number:int, chunk:bytes, timestamp: float) -> None:
        try:
            audio_chunk = AudioChunk(sequence_number= sequence_number, audio_data= chunk, timestamp= timestamp)
            self.queue.put(audio_chunk)
        except Full:
            self.logger.error("Queue is full, dropping chunk")
            raise QueueFullError("Queue is full, dropping chunk")
            

    async def remove_bacth_from_queue (self, batch_size: int) ->list[AudioChunk]:
        chunks = []
        try:
            while len(chunks) < batch_size:
                chunk = await self.queue.get_nowait()
                chunks.append(chunk)
        except Empty:
            self.logger.error("Queue is empty")
            raise QueueEmptyError("Queue is empty")
        return chunks