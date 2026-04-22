from pathlib import Path
import os
from http import HTTPStatus
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv
from dashscope.audio.asr import Transcription

load_dotenv()


class BailianASRProvider:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.model = os.getenv("BAILIAN_ASR_MODEL", "paraformer-v2")
        self.public_audio_base_url = os.getenv("PUBLIC_AUDIO_BASE_URL", "").strip()

        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY is not set in .env")

    def _resolve_public_url(self, audio_path: Path) -> str:
        """
        把本地文件名映射到一个公网可访问 URL。
        约定：你已经把同名文件上传到了 PUBLIC_AUDIO_BASE_URL 对应的位置。
        例如：
        PUBLIC_AUDIO_BASE_URL=https://my-bucket.oss-cn-beijing.aliyuncs.com/audio/
        audio_path=Path('demo.wav')
        -> https://my-bucket.oss-cn-beijing.aliyuncs.com/audio/demo.wav
        """
        if not self.public_audio_base_url:
            raise ValueError(
                "PUBLIC_AUDIO_BASE_URL is not set. "
                "Bailian Paraformer requires a public HTTP/HTTPS file URL."
            )

        return urljoin(
            self.public_audio_base_url.rstrip("/") + "/",
            audio_path.name,
        )

    def _parse_result_json(self, payload: dict) -> dict:
        transcripts = payload.get("transcripts", [])
        if not transcripts:
            return {"text": "", "segments": []}

        merged_text_parts = []
        segments = []

        for transcript in transcripts:
            text = transcript.get("text", "") or ""
            if text:
                merged_text_parts.append(text)

            for sentence in transcript.get("sentences", []):
                segments.append(
                    {
                        "start": sentence.get("begin_time", 0) / 1000.0,
                        "end": sentence.get("end_time", 0) / 1000.0,
                        "text": sentence.get("text", "") or "",
                    }
                )

        return {
            "text": "\n".join([t for t in merged_text_parts if t]).strip(),
            "segments": segments,
        }

    def transcribe(
        self,
        audio_path: Path,
        lang: str,
        prompt: str | None = None,
    ) -> dict:
        file_url = self._resolve_public_url(audio_path)

        kwargs = {
            "model": self.model,
            "file_urls": [file_url],
            "api_key": self.api_key,
        }

        # 官方文档说明 language_hints 只支持 paraformer-v2
        if self.model == "paraformer-v2" and lang in {"zh", "en", "ja", "ko", "de", "fr", "ru"}:
            kwargs["language_hints"] = [lang]

        task_response = Transcription.async_call(**kwargs)
        wait_response = Transcription.wait(
            task=task_response.output.task_id,
            api_key=self.api_key,
        )

        if wait_response.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"Bailian ASR task failed: status_code={wait_response.status_code}, "
                f"response={wait_response}"
            )

        results = wait_response.output.get("results", [])
        if not results:
            raise RuntimeError(f"No ASR results returned. response={wait_response.output}")

        first_result = results[0]
        if first_result.get("subtask_status") != "SUCCEEDED":
            raise RuntimeError(
                f"ASR subtask failed: code={first_result.get('code')}, "
                f"message={first_result.get('message')}"
            )

        transcription_url = first_result.get("transcription_url")
        if not transcription_url:
            raise RuntimeError(f"No transcription_url found. result={first_result}")

        with httpx.Client(timeout=120.0) as client:
            resp = client.get(transcription_url)
            resp.raise_for_status()
            payload = resp.json()

        return self._parse_result_json(payload)