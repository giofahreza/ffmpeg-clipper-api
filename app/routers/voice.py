"""Router for /api/v1/audio/generate-voice endpoint."""

import logging
import uuid
from fastapi import APIRouter, BackgroundTasks

from app.models.common import AcceptedResponse, ErrorPayload
from app.models.voice import (
    VoiceRequest,
    VoiceSuccessPayload
)
from app.services.gdrive import (
    create_drive_client,
    validate_google_drive,
    upload_to_google_drive
)
from app.services.voice_gen import generate_speech, save_audio, get_audio_duration
from app.utils.job_dir import job_directory
from app.utils.webhook import send_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_voice_generation(job_id: str, request: VoiceRequest):
    """Background task for voice generation."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Generate speech
            audio_bytes = generate_speech(
                text=request.text_script,
                api_key=request.elevenlabs_settings.api_key,
                voice_id=request.elevenlabs_settings.voice_id,
                model_id=request.elevenlabs_settings.model_id
            )

            # Save to file
            audio_path = f"{job_dir}/voiceover.mp3"
            save_audio(audio_bytes, audio_path)

            # Get duration
            duration = get_audio_duration(audio_path)

            # Upload to Drive
            drive = create_drive_client(credentials)
            audio_url, audio_file_id = upload_to_google_drive(
                drive,
                audio_path,
                request.google_drive.target_folder_id,
                mime_type="audio/mpeg"
            )

            # Send success webhook
            payload = VoiceSuccessPayload(
                audio_file_id=audio_file_id,
                audio_url=audio_url,
                duration_seconds=duration
            )
            await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Voice generation failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


@router.post("/generate-voice", response_model=AcceptedResponse)
async def generate_voice_endpoint(
    request: VoiceRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate speech from text using ElevenLabs.

    Returns 202 Accepted immediately and processes in background.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_voice_generation, job_id, request)

    return AcceptedResponse(job_id=job_id)
