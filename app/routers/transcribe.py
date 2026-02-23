"""Router for /api/v1/audio/transcribe endpoint."""

import logging
import uuid
from fastapi import APIRouter, BackgroundTasks

from app.models.common import AcceptedResponse, ErrorPayload
from app.models.transcribe import (
    TranscribeRequest,
    TranscribeSuccessPayload
)
from app.services.gdrive import (
    create_drive_client,
    validate_google_drive,
    download_from_google_drive,
    upload_to_google_drive
)
from app.services.transcription import extract_audio_from_video, transcribe_audio
from app.utils.job_dir import job_directory
from app.utils.webhook import send_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_transcription(job_id: str, request: TranscribeRequest):
    """Background task for transcription."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Download source file
            drive = create_drive_client(credentials)
            source_file = f"{job_dir}/source.mp4"
            download_from_google_drive(
                drive,
                request.google_drive.source_file_id,
                source_file
            )

            # Extract audio
            audio_file = f"{job_dir}/audio.wav"
            extract_audio_from_video(source_file, audio_file)

            # Transcribe
            srt_content, full_transcript = transcribe_audio(
                audio_file,
                model_size=request.transcription_settings.model_size,
                compute_type=request.transcription_settings.compute_type,
                language=request.transcription_settings.language_hint
            )

            # Save SRT file
            srt_path = f"{job_dir}/captions.srt"
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

            # Upload to Drive
            srt_url, srt_file_id = upload_to_google_drive(
                drive,
                srt_path,
                request.google_drive.target_folder_id,
                mime_type="text/plain"
            )

            # Send success webhook
            payload = TranscribeSuccessPayload(
                srt_file_id=srt_file_id,
                srt_url=srt_url,
                text_summary=full_transcript
            )
            await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


@router.post("/transcribe", response_model=AcceptedResponse)
async def transcribe_endpoint(
    request: TranscribeRequest,
    background_tasks: BackgroundTasks
):
    """
    Transcribe video/audio to SRT subtitles using faster-whisper.

    Returns 202 Accepted immediately and processes in background.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_transcription, job_id, request)

    return AcceptedResponse(job_id=job_id)
