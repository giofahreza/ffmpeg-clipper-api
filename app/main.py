"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ffmpeg_compose, transcribe, voice, edit, smart_clips

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(
    title="Video & Audio Processing API",
    description="Stateless media processing for n8n workflows",
    version="1.0.0"
)

# CORS middleware for n8n integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"ok": True}


# Register routers
app.include_router(smart_clips.router, prefix="/api/v1", tags=["Video"])
app.include_router(ffmpeg_compose.router, prefix="/api/v1", tags=["Video"])
app.include_router(transcribe.router, prefix="/api/v1/audio", tags=["Audio"])
app.include_router(voice.router, prefix="/api/v1/audio", tags=["Audio"])
app.include_router(edit.router, prefix="/api/v1/audio", tags=["Audio"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
