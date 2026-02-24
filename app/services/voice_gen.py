"""Text-to-speech generation using ElevenLabs API."""

import logging
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment

logger = logging.getLogger(__name__)


def generate_speech(
    text: str,
    api_key: str,
    voice_id: str = "Rachel",
    model_id: str = "eleven_multilingual_v2"
) -> bytes:
    """
    Generate speech from text using ElevenLabs.

    Args:
        text: Text script to convert to speech
        api_key: ElevenLabs API key
        voice_id: Voice identifier
        model_id: TTS model identifier

    Returns:
        MP3 audio bytes
    """
    client = ElevenLabs(api_key=api_key)

    logger.info(f"Generating speech with voice: {voice_id}")

    audio = client.generate(
        text=text,
        voice=voice_id,
        model=model_id
    )

    # Convert generator to bytes
    audio_bytes = b"".join(audio)

    logger.info(f"Generated {len(audio_bytes)} bytes of audio")

    return audio_bytes


def save_audio(audio_bytes: bytes, output_path: str) -> None:
    """
    Save audio bytes to file.

    Args:
        audio_bytes: MP3 audio data
        output_path: Output file path
    """
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"Saved audio to {output_path}")


def get_audio_duration(audio_path: str) -> float:
    """
    Get audio duration in seconds.

    Args:
        audio_path: Path to audio file

    Returns:
        Duration in seconds
    """
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio) / 1000.0  # Convert milliseconds to seconds

    logger.info(f"Audio duration: {duration:.2f} seconds")

    return duration
