"""Unified smart clips router - analyzes once, generates flexibly."""

import logging
import uuid
from typing import List
from fastapi import APIRouter, BackgroundTasks

from app.models.common import AcceptedResponse, ErrorPayload
from app.models.smart_clips import (
    SmartClipsRequest,
    SmartClipsAnalyzePayload,
    SmartClipsGeneratePayload,
    AnalyzedSegment,
    GeneratedClip
)
from app.services.gdrive import (
    create_drive_client,
    validate_google_drive,
    download_from_google_drive,
    upload_to_google_drive
)
from app.services.auto_shorts import (
    get_video_metadata,
    detect_scenes,
    transcribe_with_timestamps,
    generate_candidate_segments,
    select_top_segments,
    calculate_speech_energy,
    calculate_face_presence,
    count_scene_changes,
    extract_keywords
)
from app.services.cutter import create_vertical_clip, extract_segment
from app.services.finisher import burn_captions
from app.services.transcription import format_timestamp
from app.utils.job_dir import job_directory
from app.utils.webhook import send_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_smart_clips(job_id: str, request: SmartClipsRequest):
    """Unified background task for all smart clip modes."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Download source video ONCE
            logger.info(f"Mode: {request.settings.mode}")
            drive = create_drive_client(credentials)
            source_video = f"{job_dir}/source.mp4"
            download_from_google_drive(
                drive,
                request.google_drive.source_file_id,
                source_video
            )

            # Get metadata
            metadata = get_video_metadata(source_video)
            duration = metadata["duration"]

            # MODE 1: ANALYZE ONLY
            if request.settings.mode == "analyze_only":
                logger.info("Running analysis without clip generation")

                # Analyze video
                scene_times = detect_scenes(source_video)
                transcription = transcribe_with_timestamps(source_video)

                # Generate candidates
                candidates = generate_candidate_segments(
                    duration,
                    transcription,
                    request.settings.target_duration,
                    request.settings.min_duration,
                    request.settings.max_duration
                )

                # Score all segments
                weights = {
                    "speech_energy_weight": request.settings.speech_energy_weight,
                    "face_presence_weight": request.settings.face_presence_weight,
                    "scene_change_weight": request.settings.scene_change_weight,
                    "caption_keywords_weight": request.settings.caption_keywords_weight
                }

                analyzed = []
                for i, (start, end) in enumerate(candidates[:20], 1):  # Top 20 candidates
                    # Calculate individual scores
                    speech = calculate_speech_energy(transcription, start, end)
                    face = calculate_face_presence(source_video, start, end)
                    scenes = count_scene_changes(scene_times, start, end)
                    keywords = extract_keywords(transcription, start, end)

                    # Total score
                    total_score = (
                        speech * weights["speech_energy_weight"] +
                        face * weights["face_presence_weight"] +
                        min(scenes / 3.0, 1.0) * weights["scene_change_weight"] +
                        min(len(keywords) / 5.0, 1.0) * weights["caption_keywords_weight"]
                    )

                    analyzed.append(AnalyzedSegment(
                        segment_number=i,
                        start_time=start,
                        end_time=end,
                        duration=end - start,
                        virality_score=total_score,
                        keywords=keywords,
                        speech_energy=speech,
                        face_presence=face,
                        scene_changes=scenes,
                        keyword_count=len(keywords)
                    ))

                # Sort by score
                analyzed.sort(key=lambda x: x.virality_score, reverse=True)

                # Generate recommendation
                top_score = analyzed[0].virality_score if analyzed else 0
                if top_score > 0.7:
                    recommendation = f"Found {len(analyzed)} segments. Top {min(3, len(analyzed))} have excellent viral potential (score > 0.7)."
                elif top_score > 0.5:
                    recommendation = f"Found {len(analyzed)} segments. Top {min(3, len(analyzed))} have good viral potential (score > 0.5)."
                else:
                    recommendation = f"Found {len(analyzed)} segments. Consider adjusting weights or source content."

                payload = SmartClipsAnalyzePayload(
                    analyzed_segments=analyzed,
                    total_segments=len(analyzed),
                    source_duration=duration,
                    recommendation=recommendation
                )
                await send_webhook(request.webhook_callback, payload.model_dump())

            # MODE 2: AUTO GENERATE
            elif request.settings.mode == "auto_generate":
                logger.info("Running auto-discovery with clip generation")

                # Full AI pipeline
                scene_times = detect_scenes(source_video)
                transcription = transcribe_with_timestamps(source_video)

                candidates = generate_candidate_segments(
                    duration,
                    transcription,
                    request.settings.target_duration,
                    request.settings.min_duration,
                    request.settings.max_duration
                )

                weights = {
                    "speech_energy_weight": request.settings.speech_energy_weight,
                    "face_presence_weight": request.settings.face_presence_weight,
                    "scene_change_weight": request.settings.scene_change_weight,
                    "caption_keywords_weight": request.settings.caption_keywords_weight
                }

                top_segments = select_top_segments(
                    source_video,
                    candidates,
                    transcription,
                    scene_times,
                    request.settings.max_clips,
                    weights
                )

                clips = await generate_clips_from_segments(
                    source_video,
                    top_segments,
                    transcription,
                    drive,
                    request,
                    job_dir,
                    auto_mode=True
                )

                payload = SmartClipsGeneratePayload(
                    mode="auto_generate",
                    clips=clips,
                    total_clips=len(clips),
                    source_duration=duration
                )
                await send_webhook(request.webhook_callback, payload.model_dump())

            # MODE 3: MANUAL GENERATE
            elif request.settings.mode == "manual_generate":
                logger.info("Generating clips from manual timestamps")

                if not request.settings.manual_timestamps:
                    raise ValueError("manual_timestamps required for manual_generate mode")

                # Transcribe for captions (if needed)
                transcription = None
                if request.settings.add_captions:
                    transcription = transcribe_with_timestamps(source_video)

                # Convert manual timestamps to segment format
                manual_segments = []
                for i, ts in enumerate(request.settings.manual_timestamps):
                    manual_segments.append({
                        "start": ts.start,
                        "end": ts.end,
                        "duration": ts.end - ts.start,
                        "score": None,  # No scoring in manual mode
                        "keywords": []
                    })

                clips = await generate_clips_from_segments(
                    source_video,
                    manual_segments,
                    transcription,
                    drive,
                    request,
                    job_dir,
                    auto_mode=False
                )

                payload = SmartClipsGeneratePayload(
                    mode="manual_generate",
                    clips=clips,
                    total_clips=len(clips),
                    source_duration=duration
                )
                await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Smart clips processing failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


async def generate_clips_from_segments(
    source_video: str,
    segments: list,
    transcription: list,
    drive,
    request: SmartClipsRequest,
    job_dir: str,
    auto_mode: bool
) -> List[GeneratedClip]:
    """Generate and upload clips from segments."""
    clips = []

    for i, segment in enumerate(segments):
        clip_num = i + 1
        start = segment["start"]
        end = segment["end"]

        # Extract segment
        segment_path = f"{job_dir}/segment_{clip_num}.mp4"
        extract_segment(source_video, start, end, segment_path)

        # Create vertical clip
        vertical_path = f"{job_dir}/vertical_{clip_num}.mp4"
        create_vertical_clip(
            segment_path,
            vertical_path,
            aspect_ratio=request.settings.aspect_ratio,
            apply_face_tracking=request.settings.apply_face_tracking,
            crop_mode=request.settings.crop_mode
        )

        # Add captions if requested
        final_path = vertical_path
        if request.settings.add_captions and transcription:
            segment_transcription = [
                seg for seg in transcription
                if seg["start"] >= start and seg["end"] <= end
            ]

            if segment_transcription:
                srt_content = []
                for j, seg in enumerate(segment_transcription, 1):
                    seg_start = seg["start"] - start
                    seg_end = seg["end"] - start

                    srt_content.append(str(j))
                    srt_content.append(
                        f"{format_timestamp(seg_start)} --> {format_timestamp(seg_end)}"
                    )
                    srt_content.append(seg["text"])
                    srt_content.append("")

                srt_path = f"{job_dir}/captions_{clip_num}.srt"
                with open(srt_path, "w") as f:
                    f.write("\n".join(srt_content))

                final_path = f"{job_dir}/final_{clip_num}.mp4"
                burn_captions(
                    vertical_path,
                    srt_path,
                    final_path,
                    font=request.settings.caption_font,
                    font_size=request.settings.caption_font_size,
                    primary_color=request.settings.caption_color
                )

        # Upload to Drive
        drive_url, drive_file_id = upload_to_google_drive(
            drive,
            final_path,
            request.google_drive.target_folder_id,
            mime_type="video/mp4"
        )

        clips.append(GeneratedClip(
            clip_number=clip_num,
            drive_url=drive_url,
            drive_file_id=drive_file_id,
            start_time=start,
            end_time=end,
            duration=segment["duration"],
            virality_score=segment["score"] if auto_mode else None,
            keywords=segment["keywords"] if auto_mode else None
        ))

        logger.info(f"Generated clip #{clip_num}: {start:.1f}-{end:.1f}s")

    return clips


@router.post("/smart-clips", response_model=AcceptedResponse)
async def smart_clips_endpoint(
    request: SmartClipsRequest,
    background_tasks: BackgroundTasks
):
    """
    Unified smart clips endpoint with 3 modes:

    1. analyze_only - Just analyze and return scored segments (no clips generated)
    2. auto_generate - AI finds best moments and generates clips
    3. manual_generate - Generate clips from your timestamps

    Downloads video once, processes efficiently.

    Returns 202 Accepted immediately and processes in background.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_smart_clips, job_id, request)

    return AcceptedResponse(job_id=job_id)
