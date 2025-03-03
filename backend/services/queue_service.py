from asyncio import Queue, QueueFull, QueueEmpty 
from dataclasses import dataclass
import logging
import asyncio
from typing import List 
import unittest 
from unittest.mock import MagicMock, patch 


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
        audio_chunk = AudioChunk(sequence_number= sequence_number, audio_data= chunk, timestamp= timestamp)
        try:
            self.queue.put_nowait(audio_chunk)
        except QueueFull:
            self.logger.error("Queue is full, dropping chunk")
            raise QueueFullError("Queue is full, dropping chunk")
            

    async def remove_batch_from_queue (self, batch_size: int) ->list[AudioChunk]:
        chunks = []
        for _ in range(batch_size):
            try:
                chunk = self.queue.get_nowait()
                chunks.append(chunk)
            except asyncio.QueueEmpty:
                self.logger.error("Queue is empty")
                raise QueueEmptyError("Queue is empty")
        return chunks


class TestQueueService(unittest.TestCase):
    """
    queue service unitests
    """

    def setUp(self):
        self.queue_service = QueueService(max_size= 3)
        self.mock_audio_chunk = MagicMock(spec=AudioChunk)


    async def test_add_to_queue_sucess (self):
        await self.queue_service.add_chunk_to_queue(1, b"audio_data", 123.45)
        self.assertFalse(self.queue_service.queue.empty())

    async def test_add_to_full_queue(self):
        await self.queue_service.add_chunk_to_queue(1, b"audio_data", 123.45)
        await self.queue_service.add_chunk_to_queue(2, b"audio_data", 123.45)
        await self.queue_service.add_chunk_to_queue(3, b"audio_data", 123.45)

        with self.assertRaises(QueueFullError):
            await asyncio.wait_for(
                    self.queue_service.add_chunk_to_queue(4, b"audio_data", 123.45),
                    timeout=1.0)

    async def test_remove_chunk_from_batch_sucess(self):
        await self.queue_service.add_chunk_to_queue(1, b"audio_data", 123.45)
        await self.queue_service.add_chunk_to_queue(2, b"audio_data", 123.46)

        chunks = await self.queue_service.remove_batch_from_queue(2)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(self.queue_service.queue.qsize(), 0)

    async def test_remove_from_empty_queue(self):
        with self.assertRaises(QueueEmptyError):
            await self.queue_service.remove_batch_from_queue(2)

    def run_async(self, test_func):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_func())

    def test_all (self):
        self.run_async(self.test_add_to_queue_sucess)
        #self.run_async(self.test_add_to_full_queue)
        self.run_async(self.test_remove_chunk_from_batch_sucess)
        self.run_async(self.test_remove_from_empty_queue)
        
if __name__ == "__main__":
    unittest.main()

