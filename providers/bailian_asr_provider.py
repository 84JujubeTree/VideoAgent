from pathlib import Path
import os
import requests
from http import HTTPStatus
from dotenv import load_dotenv
from dashscope.audio.asr import Transcription
import httpx

load_dotenv()


class BailianASRProvider:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.model = os.getenv("BAILIAN_ASR_MODEL", "paraformer-v2")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY is not set in .env")

    def _upload_to_dashscope(self, audio_path: Path) -> str:
        """上传本地音频到 DashScope 临时存储，返回 oss:// URL"""

        # 第一步：获取上传凭证
        resp = requests.get(
            "https://dashscope.aliyuncs.com/api/v1/uploads",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"action": "getPolicy", "model": self.model},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"获取上传凭证失败: {resp.text}")
        policy_data = resp.json()["data"]

        # 第二步：表单上传到 OSS 临时地址
        key = f"{policy_data['upload_dir']}/{audio_path.name}"
        with open(audio_path, "rb") as f:
            upload_resp = requests.post(
                policy_data["upload_host"],
                files={
                    "OSSAccessKeyId": (None, policy_data["oss_access_key_id"]),
                    "Signature":       (None, policy_data["signature"]),   # 注意大写S
                    "policy":          (None, policy_data["policy"]),
                    "x-oss-object-acl":       (None, policy_data["x_oss_object_acl"]),
                    "x-oss-forbid-overwrite": (None, policy_data["x_oss_forbid_overwrite"]),
                    "key":             (None, key),
                    "success_action_status": (None, "200"),
                    "file":            (audio_path.name, f, "audio/wav"),
                },
                timeout=120,
            )
        if upload_resp.status_code != 200:
            raise RuntimeError(f"上传文件到临时存储失败: {upload_resp.text}")

        return f"oss://{key}"

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
                segments.append({
                    "start": sentence.get("begin_time", 0) / 1000.0,
                    "end":   sentence.get("end_time",   0) / 1000.0,
                    "text":  sentence.get("text", "") or "",
                })
        return {
            "text": "\n".join([t for t in merged_text_parts if t]).strip(),
            "segments": segments,
        }

    def transcribe(self, audio_path: Path, lang: str, prompt: str | None = None) -> dict:
        # 1. 上传文件拿 oss:// URL
        file_url = self._upload_to_dashscope(audio_path)
        print(f"[ASR] 文件已上传: {file_url}")

        # 2. 提交转写任务，必须加 X-DashScope-OssResourceResolve: enable
        kwargs = {
            "model": self.model,
            "file_urls": [file_url],
            "api_key": self.api_key,
            # Python SDK 支持透传额外 header
            "headers": {"X-DashScope-OssResourceResolve": "enable"},
        }
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
            code = first_result.get("code")
            message = first_result.get("message")
            if code == "SUCCESS_WITH_NO_VALID_FRAGMENT":
                raise RuntimeError(
                    "ASR 未检测到有效语音片段（SUCCESS_WITH_NO_VALID_FRAGMENT）。"
                    "常见原因：1) 视频音轨是静音；2) 音频是纯背景音乐没有人声；"
                    "3) 语种与 language_hints 不匹配。请检查输入视频。"
                )
            raise RuntimeError(
                f"ASR subtask failed: code={code}, message={message}"
            )

        transcription_url = first_result.get("transcription_url")
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(transcription_url)
            resp.raise_for_status()

        return self._parse_result_json(resp.json())