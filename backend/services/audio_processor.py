from typing import Optional, Callable 
from queue import Empty
# import the other class modules
from .audio_chunk_handler import AudioChunkHandler
from .audio_transcriber import AudioTranscriber
from .audio_format_handler import AudioFormatHandler, AudioFormat
from .context_manager import ContextManager
import logging 

class ProcessingError(Exception):
    pass


class AudioProcessor:
    def __init__(self, chunk_collector: AudioChunkHandler, format_handler: AudioFormatHandler, transcriber: AudioTranscriber, context_manager: ContextManager, on_transcription: Optional[Callable[[str], None]] = None):
        self.chunk_collector = chunk_collector
        self.format_handler = format_handler
        self.transcriber = transcriber
        self.context_manager = context_manager
        self.on_transcription  = on_transcription
        self.logger = logging.getLogger(__name__)
        self.is_running = True
        self.current_audio_format = None

    
    def set_audio_format(self, mime_type: str) -> None:
        """
        Set the current mime type with data from the browser 
        """

        if self.current_audio_format is not None:
            self.logger.error(f"Audio format has already been set to: {self.current_mime_type}")
            raise ProcessingError(f"Audio format has already been set to: {self.current_audio_format}")
        
        try:
            self.current_audio_format = self.format_handler.validate_audio_format(mime_type)
            self.logger.info(f"Audio format sucessfully set to: {self.current_audio_format}")
        except Exception as e:
            self.logger.error(f"Invalid MIME type: {e}")
            raise ProcessingError(f"Invalid MIME type: {e}")

    
    def process_audio_chunk(self, audio_data: bytes, timestamp: float) -> None:
        """
        Process a single chunk of audio data
        """
        if not self.current_audio_format:
            self.logger(f"Audio format not set")
            raise ProcessingError(f"Audio format not set")
        

        try:
            # add the data to a collector 
            sequence = self.chunk_collector.add_chunk_to_queue(audio_data, timestamp)

            self.logger.debug(f"Processed chunk {sequence} of size {len(audio_data)}")
        except Exception as e:
            self.logger.error(f"Error processing audio chunk: {e}")
            raise ProcessingError(f"Error processing audio chunk: {e}")

    def process_collected_chunks(self) -> Optional[str]:
        """
        Process collected chunks into transcription 
        """
        try: 
            result = self.chunk_collector.collect_chunks_from_queue()

            if not result:
                return None
        
            audio_buffer, last_sequence, last_timestamp = result

            # convert to numpy
            audio_array = self.format_handler.convert_audio_to_numpy(audio_buffer, self.current_audio_format)

            # transcribe the audio 
            transcription = self.transcriber.transcribe(audio_array)

            # add transcription to context
            self.context_manager.add_transcription(transcription)

            if self.on_transcription:
                self.on_transcription(transcription.text)
            
            return transcription.text
        

        except Exception as e:
            self.logger.error(f"Error processing collected chunks: {e}")
            raise ProcessingError(f"Failed to process collected chunks: {e}")



    def get_current_transcript(self) -> str:
        """
        Get current transcript from context
        """
        return self.context_manager.get_current_context()

    def shutdown(self) -> None:
        """
        Clean shutdown of processor 
        """
        self.is_running = False
        self.transcriber.shutdown()