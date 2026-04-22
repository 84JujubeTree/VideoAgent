from pathlib import Path


class MockASRProvider:
    def transcribe(
        self,
        audio_path: Path,
        lang: str,
        prompt: str | None = None,
    ) -> dict:
        return {
            "text": f"[mock transcription for {audio_path.name}]",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": f"[mock transcription for {audio_path.name}]",
                }
            ],
        }