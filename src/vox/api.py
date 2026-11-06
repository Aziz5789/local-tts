"""Local web API for Vox. Routes stay thin: every workflow lives in services."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from vox.audio import encode_wav
from vox.runtime import InferenceWorker
from vox.services import (
    VoiceDetails,
    VoiceExistsError,
    VoiceNotFoundError,
    VoxInputError,
    delete_voice,
    enroll_voice,
    get_voice,
    get_voice_library,
    synthesize_speech,
    update_voice_transcript,
)

WEB_DIR = Path(__file__).parent / "web"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
LOCAL_HOSTS = ["127.0.0.1", "localhost"]
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class SpeechRequest(BaseModel):
    text: str
    voice_id: str | None = None
    engine: str | None = None


class TranscriptUpdate(BaseModel):
    transcript: str


def _voice_json(details: VoiceDetails) -> dict:
    voice = details.voice
    metadata = details.metadata

    return {
        "id": voice.voice_id,
        "display_name": voice.display_name,
        "transcript": voice.transcript,
        "transcript_generated": metadata.transcript.generated,
        "transcript_reviewed_at": metadata.transcript.reviewed_at,
        "created_at": metadata.created_at,
        "duration_seconds": metadata.audio.duration_seconds,
        "reference_url": f"/api/voices/{voice.voice_id}/reference",
    }


async def _save_upload(upload: UploadFile, directory: Path) -> Path:
    # Keep the original extension so FFmpeg can recognize the container.
    suffix = Path(upload.filename or "").suffix.lower()
    destination = directory / f"upload{suffix}"
    total_bytes = 0

    with destination.open("wb") as file:
        while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
            total_bytes += len(chunk)

            if total_bytes > MAX_UPLOAD_BYTES:
                raise VoxInputError("Audio file is larger than 100 MB.", field="audio")

            file.write(chunk)

    if total_bytes == 0:
        raise VoxInputError("Audio file is empty.", field="audio")

    return destination


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.worker = InferenceWorker()
        yield
        app.state.worker.shutdown()

    app = FastAPI(title="Vox", lifespan=lifespan)

    @app.middleware("http")
    async def reject_cross_site_writes(request: Request, call_next):
        # Listening on localhost doesn't stop other websites: any page open in
        # the browser can submit a form to 127.0.0.1. Browsers send an Origin
        # header with such requests, so only accept changes from Vox's own page.
        # Requests without one (curl, scripts) aren't from a web page.
        origin = request.headers.get("origin")
        is_cross_site = origin is not None and urlsplit(
            origin
        ).netloc != request.headers.get("host")

        if request.method in STATE_CHANGING_METHODS and is_cross_site:
            return JSONResponse(
                status_code=403,
                content={"detail": "Requests from other websites are not allowed."},
            )

        return await call_next(request)

    @app.middleware("http")
    async def revalidate(request: Request, call_next):
        # Make the browser check for a newer page or voice list on every load,
        # so an updated Vox or a voice added from the CLI is never hidden by cache.
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.exception_handler(VoxInputError)
    async def input_error(_request: Request, error: VoxInputError) -> JSONResponse:
        status_code = 409 if isinstance(error, VoiceExistsError) else 400
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(error), "field": error.field},
        )

    @app.exception_handler(VoiceNotFoundError)
    async def not_found(_request: Request, error: VoiceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(RuntimeError)
    async def runtime_error(_request: Request, error: RuntimeError) -> JSONResponse:
        # Local-only app: the real message is more useful than a generic one.
        return JSONResponse(status_code=500, content={"detail": str(error)})

    @app.get("/healthz")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/voices")
    def list_voices_route() -> dict:
        library = get_voice_library()
        return {
            "voices": [_voice_json(details) for details in library.voices],
            "invalid": [
                {"id": invalid.voice_id, "reason": invalid.reason}
                for invalid in library.invalid
            ],
        }

    @app.get("/api/voices/{voice_id}")
    def get_voice_route(voice_id: str) -> dict:
        return _voice_json(get_voice(voice_id))

    @app.get("/api/voices/{voice_id}/reference")
    def get_reference_audio(voice_id: str) -> FileResponse:
        details = get_voice(voice_id)
        return FileResponse(details.voice.reference_path, media_type="audio/wav")

    @app.post("/api/voices", status_code=201)
    async def create_voice(
        request: Request,
        audio: Annotated[UploadFile, File()],
        voice_id: Annotated[str, Form()],
        display_name: Annotated[str | None, Form()] = None,
        transcript: Annotated[str | None, Form()] = None,
    ) -> dict:
        with TemporaryDirectory(prefix="vox-upload-") as temporary_directory:
            audio_path = await _save_upload(audio, Path(temporary_directory))
            details = await request.app.state.worker.run(
                enroll_voice,
                audio_path=audio_path,
                voice_id=voice_id,
                display_name=display_name or None,
                transcript=transcript if transcript and transcript.strip() else None,
                original_filename=audio.filename,
            )

        return _voice_json(details)

    @app.put("/api/voices/{voice_id}/transcript")
    def update_transcript_route(voice_id: str, update: TranscriptUpdate) -> dict:
        return _voice_json(update_voice_transcript(voice_id, update.transcript))

    @app.delete("/api/voices/{voice_id}", status_code=204)
    def delete_voice_route(voice_id: str) -> Response:
        delete_voice(voice_id)
        return Response(status_code=204)

    @app.post("/api/speech")
    async def create_speech(request: Request, speech: SpeechRequest) -> Response:
        # Picking a stored voice implies the cloning engine.
        engine_name = speech.engine or ("qwen" if speech.voice_id else "kokoro")
        result = await request.app.state.worker.run(
            synthesize_speech,
            text=speech.text,
            engine_name=engine_name,
            voice_id=speech.voice_id,
        )
        return Response(content=encode_wav(result), media_type="audio/wav")

    # Registered last so the API routes above take priority over static files.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    # A site can point its own domain at 127.0.0.1 (DNS rebinding) to read
    # this API as if it were same-origin. Its requests still carry its domain
    # in the Host header, so answer only requests addressed to this machine.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    return app
