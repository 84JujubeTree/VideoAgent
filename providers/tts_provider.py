from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(
        self,
        text: str,
        output_path: Path,
        voice_prompt_path: str | None = None,
    ) -> dict:
        """
        Return normalized result:
        {
            "audio_path": "...",
            "duration": 1.23
        }
        """
        ...