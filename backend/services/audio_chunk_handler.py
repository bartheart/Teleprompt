from dataclasses import dataclass
from queue import Queue, Empty, Full
from typing import Optional, Tuple
from io import BytesIO
import logging
import pytest
import time 
import struct 



class BufferQueueFull(Exception):
    pass

class BufferQueueEmpty(Exception):
    pass

class ChunkProcessingError(Exception):
    pass

@dataclass 
class AudioChunk:
    """
    define the data structure for the audio chunk
    """
    sequence_number: int
    audio_data: bytes
    timestamp: float 
    header: bytes 
    metadata: dict



class AudioChunkHandler:
    """
    handle audio chunks
    """
    def __init__ (self):
        self.buffer_queue = Queue(maxsize=40)
        self.sequence_counter = 0
        self.min_chunk_to_process = 10
        self.logger = logging.getLogger(__name__)

    
    def generate_header(self, sample_rate=16000, channels=1, bit_depth=16):
        pass

    
    def add_chunk_to_queue(self, audio_chunk: bytes, timestamp: float) -> int:
        """      
        add the audio chunk to the buffer queue
        """
        try:
            chunk = AudioChunk(self.sequence_counter, audio_chunk, timestamp)
            self.buffer_queue.put_nowait(chunk)
            current_sequence = self.sequence_counter
            self.sequence_counter = current_sequence + 1
            return current_sequence
        except Full:
            self.logger.warning("Buffer queue is full, dropping chunk")
            raise BufferQueueFull("Buffer queue is full")
        
        
    def collect_chunks_from_queue(self) -> Optional[Tuple[bytes, int, float]]:
        """
        collect the chunks from the buffer queue
        """
        audio_buffer = BytesIO()
        chunk_processed = 0
        last_sequence = None
        last_timestamp = None

        try:
            while chunk_processed < self.min_chunk_to_process:
                try:
                    chunk = self.buffer_queue.get(timeout=0.1)
                    audio_buffer.write(chunk.audio_data)
                    last_sequence = chunk.sequence_number
                    last_timestamp = chunk.timestamp
                    chunk_processed += 1

                    if chunk_processed >= self.min_chunk_to_process:
                        break
                except Empty:
                    if chunk_processed > 0:
                        break
                    return None
            
            audio_buffer.seek(0)
            return audio_buffer, last_sequence, last_timestamp
                  
        except Exception as e:
            self.logger.error(f"Error collecting chunks from the buffer queue: {e}")
            raise ChunkProcessingError("Error collecting chunks from the buffer queue")
        
    
    def get_buffer_queue_size(self) -> int:
        """
        get the size of the buffer queue
        """
        return self.buffer_queue.qsize()


