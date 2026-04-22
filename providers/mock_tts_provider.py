from pathlib import Path
import wave
import struct


class MockTTSProvider:
    def synthesize(
        self,
        text: str,
        output_path: Path,
        voice_prompt_path: str | None = None,
    ) -> dict:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sample_rate = 16000
        duration_sec = 1
        n_samples = sample_rate * duration_sec

        with wave.open(str(output_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            silence = struct.pack("<h", 0)
            for _ in range(n_samples):
                wf.writeframesraw(silence)

        return {
            "audio_path": str(output_path),
            "duration": duration_sec,
        }