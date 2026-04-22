from pathlib import Path
import os
from dotenv import load_dotenv

from providers.mock_tts_provider import MockTTSProvider

load_dotenv()


class BailianTTSProvider:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY is not set in .env")

    def synthesize(
        self,
        text: str,
        output_path: Path,
        voice_prompt_path: str | None = None,
    ) -> dict:
        # 先占位，后面接真百炼 TTS
        return MockTTSProvider().synthesize(
            text=text,
            output_path=output_path,
            voice_prompt_path=voice_prompt_path,
        )