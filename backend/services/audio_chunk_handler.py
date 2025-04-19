from dataclasses import dataclass
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
class BufferConfig:
    min_chunks_to_process: int = 10
    max_buffer_size: int = 1024 * 1024
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16


class BufferManager:
    """
    manage the audio buffer
    """
    def __init__ (self, config: BufferConfig = BufferConfig()):
        self.config = config
        self.buffer = BytesIO()
        self.current_size = 0
        self.logger = logging.getLogger(__name__)

    
    def accumulate(self, audio_chunks: list[AudioChunk]) -> Optional[bytes]:
        """      
        accumulate the audio chunks in the buffer
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


