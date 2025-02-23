import asyncio

from services.queue_service import QueueService


class AudioDispatcher:
    """
    handles dipatching incoming audio packets to a queue service while sequencing them
    """
    def __init__ (self, queue_service: QueueService):
        self.queue_service = queue_service
        self.sequence_counter = 0
        self.lock = asyncio.Lock()

    async def dispatch_audio_packets (self, audio_chunk: bytes, timestamp: float) -> None :
        async with self.lock:
            sequence_number = self.sequence_counter
            self.sequence_counter += 1

        self.queue_service.add_chunk_to_queue(sequence_number, audio_chunk, timestamp)

    