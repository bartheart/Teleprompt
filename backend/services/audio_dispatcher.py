import unittest
import logging
from services.queue_service import QueueService, QueueFullError
from unittest.mock import AsyncMock, MagicMock 

class AudioDispatcher:
    """
    handles dipatching incoming audio packets to a queue service while sequencing them
    """
    def __init__ (self, queue_service: QueueService):
        self.queue_service = queue_service
        self.sequence_counter = 0
        self.logger = logging.getLogger(__name__)

    async def dispatch_audio_packet (self, audio_chunk: bytes, timestamp: float) -> int:
        """
        version the audio packet and attempt adding to a queue 
        """

        sequence_number = self.sequence_counter
        try:
            await self.queue_service.add_chunk_to_queue(sequence_number, audio_chunk, timestamp)  
            self.sequence_counter += 1
            self.logger.info(f"Dispatched chunk with sequence number: {sequence_number}")
            return sequence_number
        except QueueFullError:
            self.logger.warning(f"Queue is full, dropping chunk {sequence_number}")
            raise


class TestAudioDispatcher(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_audio_packet_sucess(self):
        queue_service_mock = AsyncMock(spec=QueueService)
        dispatcher = AudioDispatcher(queue_service_mock)

        audio_chunk = b"test_audio"
        timestamp = 123.45

        sequence_number = await dispatcher.dispatch_audio_packet(audio_chunk, timestamp)

        queue_service_mock.add_chunk_to_queue.assert_awaited_once_with(0, audio_chunk, timestamp)
        self.assertEqual(sequence_number, 0)
        self.assertEqual(dispatcher.sequence_counter, 1)


    async def test_dispatch_audio_packet_full(self):
        queue_service_mock = AsyncMock(spec=QueueService)
        queue_service_mock.add_chunk_to_queue.side_effect = QueueFullError

        dispatcher = AudioDispatcher(queue_service_mock)

        audio_chunk = b"test_audio"
        timestamp = 123.45

        with self.assertRaises(QueueFullError):
            await dispatcher.dispatch_audio_packet(audio_chunk, timestamp)

        queue_service_mock.add_chunk_to_queue.assert_awaited_once_with(0, audio_chunk, timestamp)
        self.assertEqual(dispatcher.sequence_counter, 0)

if __name__ == "__main__":
    unittest.main()

