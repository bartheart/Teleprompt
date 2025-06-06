import pytest
import queue
import logging
from dataclasses import dataclass

@dataclass 
class AudioChunk:
    sequence_number: int
    audio_data: bytes
    timestamp: float


class AudioQueue:

    def __init__ (self, max_size: int = 40):
        self.queue = queue.Queue(maxsize=max_size)
        self.logger = logging.getLogger(__name__)

    def enqueue (self, audio_chunk: AudioChunk) -> None:
        if audio_chunk is None:
            self.logger.error("Invalid audio chunk, skipping")
            return
        try:
            self.queue.put(audio_chunk)
            self.logger.info(f"Audio chunk enqueued with sequence number: {audio_chunk.sequence_number}")
        except queue.Full:
            self.logger.error("Queue is full, dropping chunk")
            raise

    def _dequeue (self) -> AudioChunk:
        try: 
            dequeued_audio_chunk = self.queue.get_nowait()
            self.logger.info(f"Audio chunk dequeued with sequence number: {dequeued_audio_chunk.sequence_number}")
            return dequeued_audio_chunk
        except queue.Empty:
            self.logger.error("Error dequeueing from an empty queue")
            return 

    def dequeue_batch (self, batch_size = 10) -> list[AudioChunk]:
        if self.queue.qsize() < batch_size:
            self.logger.error(f"Not enough amount of chunks in the queue")
            return 
        
        audio_chunk_batch = []
        for _ in range(batch_size):
            try: 
                dequeued_audio_chunk = self._dequeue()
            except Exception as e:
                self.logger.error("Error dequeueing an auido chunk: {e}")
                return 
            audio_chunk_batch.append(dequeued_audio_chunk)
            
        return audio_chunk_batch





@pytest.fixture
def audio_queue():
    return AudioQueue(max_size=3)

@pytest.fixture
def audio_chunk():
    return AudioChunk(
        sequence_number=0,
        audio_data=b"test_audio",
        timestamp=123.45
    )

@pytest.fixture
def audio_queue_20_chunks(audio_chunk):
    audio_queue = AudioQueue()
    for _ in range(20):
        audio_queue.enqueue(audio_chunk)
    return audio_queue

def test_queue_initialization(audio_queue):
    assert audio_queue.queue.empty()
    assert audio_queue.queue.maxsize == 3
    assert isinstance(audio_queue.queue, queue.Queue)


def test_enqueue(audio_queue, audio_chunk):
    audio_queue.enqueue(audio_chunk)
    assert not audio_queue.queue.empty()
    assert audio_queue.queue.qsize() == 1

def test_dequeue(audio_queue, audio_chunk):
    audio_queue.enqueue(audio_chunk)
    assert audio_queue.queue.qsize() == 1
    dequeued_audio_chunk = audio_queue._dequeue()
    assert audio_queue.queue.qsize() == 0
    assert audio_queue.queue.empty()
    assert isinstance(dequeued_audio_chunk, AudioChunk)
    assert audio_chunk == dequeued_audio_chunk

def test_dequeue_empty(audio_queue, caplog):
    assert audio_queue.queue.qsize() == 0
    with caplog.at_level("ERROR"):
        dequeued_chunk = audio_queue._dequeue()
        assert dequeued_chunk is None 
        assert "Error dequeueing from an empty queue" in caplog.text

def test_dequeue_batch(audio_queue_20_chunks):
    assert audio_queue_20_chunks.queue.qsize() == 20
    dequed_batch = audio_queue_20_chunks.dequeue_batch(batch_size=5)
    assert len(dequed_batch) == 5
    assert audio_queue_20_chunks.queue.qsize() == 15
    dequed_batch = audio_queue_20_chunks.dequeue_batch(batch_size=10)
    assert len(dequed_batch) == 10
    assert audio_queue_20_chunks.queue.qsize() == 5
    dequed_batch = audio_queue_20_chunks.dequeue_batch(batch_size=15)
    assert dequed_batch is None
    assert audio_queue_20_chunks.queue.qsize() == 5

    


if __name__ == '__main__':
    pytest.main([__file__])
