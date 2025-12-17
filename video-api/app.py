from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI()


class GenerateRequest(BaseModel):
    audioContent: str = Field(..., description="Base64-encoded MP3 bytes")
    imagePath: str = Field("/assets/avatar.png", description="Path to avatar image inside container")


@app.post("/generate")
def generate(req: GenerateRequest):
    # 0) validate image path
    if not os.path.exists(req.imagePath):
        raise HTTPException(status_code=400, detail=f"image not found: {req.imagePath}")

    # 1) decode audio base64 -> bytes
    try:
        audio_bytes = base64.b64decode(req.audioContent, validate=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid audioContent base64: {e}")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audioContent is empty after base64 decode")

    # 2) create output path that will NOT disappear during FileResponse
    final_mp4_path = f"/tmp/output-{uuid.uuid4().hex}.mp4"

    # 3) work in a temp dir, then move mp4 to /tmp
    with tempfile.TemporaryDirectory() as d:
        mp3_path = os.path.join(d, "audio.mp3")
        tmp_mp4_path = os.path.join(d, "output.mp4")

        # write mp3
        with open(mp3_path, "wb") as f:
            f.write(audio_bytes)

        # ffmpeg: image + audio -> mp4
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            req.imagePath,
            "-i",
            mp3_path,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            tmp_mp4_path,
        ]

        p = subprocess.run(cmd, capture_output=True, text=True)

        if p.returncode != 0:
            # return ffmpeg stderr for debugging
            raise HTTPException(
                status_code=500,
                detail=(
                    "ffmpeg failed\n"
                    f"cmd: {' '.join(cmd)}\n"
                    f"stdout:\n{p.stdout}\n"
                    f"stderr:\n{p.stderr}\n"
                ),
            )

        if not os.path.exists(tmp_mp4_path):
            raise HTTPException(status_code=500, detail="mp4 was not created (tmp_mp4_path not found)")

        # move to persistent path so FileResponse can read it
        os.replace(tmp_mp4_path, final_mp4_path)

    # 4) respond
    return FileResponse(
        final_mp4_path,
        media_type="video/mp4",
        filename="output.mp4",
    )
