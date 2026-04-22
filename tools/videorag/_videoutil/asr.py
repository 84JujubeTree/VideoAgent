import os
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


def _get_asr_provider():
    provider_name = os.getenv("ASR_PROVIDER", "mock").lower()

    if provider_name == "bailian":
        from providers.bailian_asr_provider import BailianASRProvider
        return BailianASRProvider()

    from providers.mock_asr_provider import MockASRProvider
    return MockASRProvider()


def speech_to_text(video_name, working_dir, segment_index2name, audio_output_format):
    """
    Convert cached segment audio files to text using the unified ASR provider.
    """
    provider = _get_asr_provider()
    cache_path = os.path.join(working_dir, "_cache", video_name)

    transcripts = {}

    for index in tqdm(segment_index2name, desc=f"Speech Recognition {video_name}"):
        segment_name = segment_index2name[index]
        audio_file = os.path.join(cache_path, f"{segment_name}.{audio_output_format}")

        result = provider.transcribe(
            Path(audio_file),
            lang="zh",
            prompt=None,
        )

        formatted_result = ""

        if "segments" in result and result["segments"]:
            for seg in result["segments"]:
                start = seg.get("start", 0) or 0
                end = seg.get("end", 0) or 0
                text = seg.get("text", "") or ""
                formatted_result += f"[{start:.2f}s -> {end:.2f}s] {text}\n"
        else:
            text = result.get("text", "") or ""
            formatted_result = text

        transcripts[index] = formatted_result

    return transcripts