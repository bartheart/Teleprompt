from dataclasses import dataclass
from typing import Dict, Optional 
from io import BytesIO
from pydub import AudioSegment
import numpy as np 
import logging


class AudioFormatError(Exception):
    pass

class ConversionError(Exception):
    pass

@ dataclass
class AudioFormat:
    mime_type: str
    sample_rate: int
    codec: str


class AudioFormatHandler:
    """
    Audio format handler
    """
    def __init__ (self):
        sample_rate = 16000
        self.logger = logging.getLogger(__name__)
        self.audio_formats: Dict[str: AudioFormat] = {
            'audio/webm': AudioFormat('webm', sample_rate, 'opus'),
            'audio/webm;codecs=opus': AudioFormat('webm', sample_rate, 'opus'),
            'audio/mp4': AudioFormat('mp4', sample_rate, 'opus'),
            'audio/mp4;codecs=opus': AudioFormat('mp4', sample_rate, 'opus'),
            'audio/ogg': AudioFormat('ogg', sample_rate, 'opus'),
            'audio/ogg;codecs=opus': AudioFormat('ogg', sample_rate, 'opus'),
        }

    def validate_audio_format (self, mime_type: str) -> Optional[AudioFormat]:
        """
        validate the audio format
        """
        if mime_type not in self.audio_formats:
            self.logger.error(f'Unspported audio format: {mime_type}')
            raise AudioFormatError(f'Unsupported audio format: {mime_type}')
        return self.audio_formats.get(mime_type)
    

    def convert_audio_to_numpy (self, audio_chunks_collection: BytesIO, audio_format: AudioFormat) -> np.ndarray:
        """
        convert the audio chunks to numpy array
        """
        try:
            audio_stream = b"".join(chunk for chunk in audio_chunks_collection)

            audio_segment = AudioSegment.from_file(BytesIO(audio_stream), format=audio_format.mime_type)

            # audio_segment = AudioSegment.from_file(
            #     audio_chunks_collection, 
            #     format= audio_format.mime_type,
            #     codec= audio_format.codec,
            #     parameters= [
            #             "-loglevel", "debug", 
            #             "-ar", str(audio_format.sample_rate),
            #             "-ac", "1",  
            #             "-vn"
            #         ]
            #     )
            
            # convert to numpy array 
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / 32768.0

            self.logger.debug(f"Converted audio: shape={samples.shape}, sr={audio_format.sample_rate}")
            return samples
        
        except Exception as e:
            self.logger.error(f"Failed to convert audio to numpy: {e}")
            raise ConversionError(f"Failed to convert audio to numpy: {e}")