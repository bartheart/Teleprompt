import pytest
from time import time
import numpy as np
from unittest.mock import Mock, patch
from services.audio_chunk_handler import AudioChunkHandler
from services.audio_transcriber import AudioTranscriber
from services.audio_format_handler import AudioFormatHandler, AudioFormat
from services.context_manager import ContextManager
from services.audio_processor import AudioProcessor, ProcessingError

@pytest.fixture
def mock_components():
    return {
        'chunk_collector': Mock(spec=AudioChunkHandler),
        'format_handler': Mock(spec=AudioFormatHandler),
        'transcriber': Mock(spec=AudioTranscriber),
        'context_manager': Mock(spec=ContextManager),
    }

def test_process_audio_chunk(mock_components):
    processor = AudioProcessor(**mock_components)
    
    # Test processing a chunk
    audio_data = b'test_audio'
    mime_type = 'audio/webm'
    timestamp = time.time()
    
    mock_components['format_handler'].validate_audio_format.return_value = Mock()
    mock_components['chunk_collector'].add_chunk_to_queue.return_value = 1
    
    processor.process_audio_chunk(audio_data, mime_type, timestamp)
    
    mock_components['format_handler'].validate_audio_format.assert_called_once_with(mime_type)
    mock_components['chunk_collector'].add_chunk_to_queue.assert_called_once()

def test_process_collected_chunks(mock_components):
    processor = AudioProcessor(**mock_components)
    
    # Mock collect_chunks_from_queue to return proper tuple
    mock_components['chunk_collector'].collect_chunks_from_queue.return_value = (
        b'test_audio',  # audio_buffer
        1,             # last_sequence
        123.45        # last_timestamp
    )
    
    # Mock format validation and conversion
    mock_components['format_handler'].validate_audio_format.return_value = 'audio/wav'
    mock_components['format_handler'].convert_audio_to_numpy.return_value = np.zeros(1000)
    
    # Mock transcription
    mock_transcription = Mock()
    mock_transcription.text = "test transcription"
    mock_components['transcriber'].transcribe.return_value = mock_transcription
    
    # Test the method
    result = processor.process_collected_chunks()
    
    # Assertions
    assert result == "test transcription"
    mock_components['chunk_collector'].collect_chunks_from_queue.assert_called_once()
    mock_components['format_handler'].convert_audio_to_numpy.assert_called_once()
    mock_components['transcriber'].transcribe.assert_called_once()
    mock_components['context_manager'].add_transcription.assert_called_once_with(mock_transcription)

def test_callback_execution(mock_components):
    callback = Mock()
    processor = AudioProcessor(**mock_components, on_transcription=callback)
    
    # Mock successful transcription chain
    mock_components['chunk_collector'].collect_chunks_from_queue.return_value = (b'audio_data', 1, time.time())
    mock_components['format_handler'].validate_audio_format.return_value = 'audio/wav'
    mock_components['format_handler'].convert_audio_to_numpy.return_value = np.zeros(1000)
    mock_transcription = Mock(text="test")
    mock_components['transcriber'].transcribe.return_value = mock_transcription
    
    processor.process_collected_chunks()
    callback.assert_called_once_with("test")

def test_error_handling(mock_components):
    processor = AudioProcessor(**mock_components)
    
    # Test error in format validation
    mock_components['format_handler'].validate_audio_format.side_effect = Exception("Format error")
    
    with pytest.raises(ProcessingError):
        processor.process_audio_chunk(b'test', 'audio/webm', time.time())

@pytest.mark.integration
def test_full_integration():
    """Full integration test with real components"""
    chunk_collector = AudioChunkHandler()
    format_handler = AudioFormatHandler()
    transcriber = AudioTranscriber(model_name="base", num_workers=1)
    context_manager = ContextManager()
    
    processor = AudioProcessor(
        chunk_collector,
        format_handler, 
        transcriber,
        context_manager
    )
    
    sample_audio = np.zeros(16000, dtype=np.float32)
    audio_bytes = sample_audio.tobytes()
    
    try:
        # Create proper AudioFormat object
        audio_format = AudioFormat('audio/webm', 16000, 16, 1)
        processor.current_mime_type = audio_format
        
        processor.process_audio_chunk(audio_bytes, 'audio/webm', time.time())
        result = processor.process_collected_chunks()
        assert isinstance(result, (str, type(None)))
    finally:
        processor.shutdown()

if __name__ == '__main__':
    pytest.main([__file__])
    
