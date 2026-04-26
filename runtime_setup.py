import os
from pathlib import Path
from pydub import AudioSegment

FFMPEG_BIN_DIR = Path(
    r"C:\Users\枣树\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
)

FFMPEG_EXE = FFMPEG_BIN_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_BIN_DIR / "ffprobe.exe"


def setup_runtime():
    os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")
    AudioSegment.converter = str(FFMPEG_EXE)
    AudioSegment.ffmpeg = str(FFMPEG_EXE)
    AudioSegment.ffprobe = str(FFPROBE_EXE)