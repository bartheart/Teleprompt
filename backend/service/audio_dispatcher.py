
import pytest
from queue import Queue 
import logging
import time 

class AudioDispatcher:
    """
    process incoming audio packets, version and timestamp them and put it on a queue    
    """
    def __init__ (self, queue: Queue):
        self.queue = queue
        self.counter = 0
        self.logger = logging.getLogger(__name__)

    def enqueue_audio_chunk (self, audio_chunk: bytes) -> None:
        if audio_chunk is None:
            self.logger.error("Invalid audio chunk, skipping")
            return
        try:
            sequence_number = self.counter

            # create a tuple for the auido chunk with timestamp and sequence 
            audio_tuple = (sequence_number, audio_chunk, time.time()) 

            self.queue.put(audio_tuple)

            self.counter += 1

            self.logger.info(f"Audio chunk enqueued with sequence number: {sequence_number}")

        except Exception as e:
            self.logger.error("Error adding audio chunk to queue: {e}")

    def get_queue_depth (self) -> int:
        return self.queue.qsize()


# test the intiatlizatipon of dispatcher class 
@pytest.fixture 
def audio_dispatcher():
    queue = Queue()
    return AudioDispatcher(queue)

def test_intialization (audio_dispatcher):
    assert hasattr(audio_dispatcher, "counter")
    assert audio_dispatcher.counter == 0
    assert isinstance(audio_dispatcher.queue, Queue)
    assert audio_dispatcher.queue.empty() == True 

# test the versioning functionality 
def test_versioning (audio_dispatcher):
    audio_chunk = b'test_audio'
    audio_dispatcher.enqueue_audio_chunk(audio_chunk)
    assert audio_dispatcher.counter == 1

    audio_dispatcher.enqueue_audio_chunk(audio_chunk)
    assert audio_dispatcher.counter == 2 

# test the timestamping functionality
def test_timestamping (audio_dispatcher):
    audio_chunk = b'test_audio'
    before_enque = time.time()
    audio_dispatcher.enqueue_audio_chunk(audio_chunk)
    after_enqueue  = time.time()

    sequence_number, chunk, timestamp = audio_dispatcher.queue.get()
    assert before_enque <= timestamp <= after_enqueue
    assert chunk == audio_chunk

    
# test error cases 
def test_error_handling (audio_dispatcher):
    invalid_chunk = None 
    audio_dispatcher.enqueue_audio_chunk(invalid_chunk)
    assert audio_dispatcher.queue.empty() == True

@pytest.mark.parametrize("audio_chunk", [
    b'',
    b'shot_audio',
    b'long_audio' * 1000
])

def test_different_size_chunks (audio_dispatcher, audio_chunk):
    audio_dispatcher.enqueue_audio_chunk(audio_chunk)
    _, stored_chunk, _ = audio_dispatcher.queue.get()
    assert stored_chunk == audio_chunk

if __name__ == '__main__':
    pytest.main([__file__])
