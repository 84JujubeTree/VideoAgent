from pathlib import Path
from typing import Protocol


class ASRProvider(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        lang: str,
        prompt: str | None = None,
    ) -> dict:
        """
        Return normalized result:
        {
            "text": "...",
            "segments": [...]
        }
        """
        ...