from dataclasses import dataclass 
from typing import List, Optional 
from io import BytesIO
import logging 
import asyncio
import unittest

@dataclass 
class BufferConfig:
    min_chunks: int = 10
    max_buffer_size: int = 1024 * 1024
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16


class BufferManager:
    def __init__ (self, config: BufferConfig = BufferConfig()):
        self.config = config
        self.buffer = BytesIO()
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)


    async def accumulate (self, chunks: List[bytes]) -> Optional[bytes]:
        async with self.lock:
            try:
                for chunk in chunks:
                    chunk_size = len(chunk)

                    # handle buffer overflow 
                    if self.buffer.tell() + chunk_size > self.config.max_buffer_size:
                        self.logger.warning("Buffer overflow, flushing")
                        return self.flush() 

                    self.buffer.write(chunk)

                self.logger.debug(f"Accumulated {len(chunks)} chunks")
                return self.buffer.getvalue()

            except Exception as e:
                self.logger.error(f"Buffer accumulation error: {e}")
                return None 
    
    def flush(self) -> bytes:
        self.logger.debug(f"Flushing a buffer of size {len(self.buffer)}")
        data = self.buffer.getvalue()
        self.reset()
        return data 


    def reset(self):
        self.buffer = BytesIO()

    def get_buffer_size(self) -> int:
        return len(self.buffer)


class TestBufferManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = BufferConfig(max_buffer_size = 1024)
        self.manager = BufferManager(config = self.config)

    async def test_accumulate(self):
        chunks = [b'testdata1', b'testdata2']
        result = await self.manager.accumulate(chunks)
        self.assertIsNotNone(result)
        self.assertEqual(result, b'testdata1testdata2')



if __name__ == "__main__":
    unittest.main()




