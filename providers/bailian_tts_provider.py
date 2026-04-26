"""
Bailian (DashScope) CosyVoice TTS Provider

参考：
  https://help.aliyun.com/zh/model-studio/cosyvoice-large-model-for-speech-synthesis
SDK 调用：
  from dashscope.audio.tts_v2 import SpeechSynthesizer
  synthesizer = SpeechSynthesizer(model='cosyvoice-v2', voice='longxiaochun_v2')
  audio_bytes = synthesizer.call('你好世界')

返回的字节流默认是 mp3 容器。本 Provider 直接落盘到 output_path。
长文本（> ~2000 字）会被自动按句号/换行切成多段拼接，避免单次超长报错。
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer
from dotenv import load_dotenv

load_dotenv()


class BailianTTSError(RuntimeError):
    pass


class BailianTTSProvider:
    # CosyVoice 单次调用建议长度上限，留点 buffer
    _MAX_CHARS_PER_CALL = 1500

    def __init__(self) -> None:
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        self.model = os.getenv("BAILIAN_TTS_MODEL", "cosyvoice-v2").strip()
        self.voice = os.getenv("BAILIAN_TTS_VOICE", "longxiaochun_v2").strip()

        if not self.api_key:
            raise BailianTTSError("DASHSCOPE_API_KEY is not set in .env")

        # SDK 既可读 env 也可显式赋值，这里都做一遍
        dashscope.api_key = self.api_key
        os.environ["DASHSCOPE_API_KEY"] = self.api_key

    # ------------------------------------------------------------------
    # 公共接口（保持与 TTSProvider Protocol 一致）
    # ------------------------------------------------------------------
    def synthesize(
        self,
        text: str,
        output_path: Path,
        voice_prompt_path: Optional[str] = None,
    ) -> dict:
        if voice_prompt_path:
            # 真要做 voice clone 需要先把样本上传到 OSS / DashScope，再用
            # cosyvoice-clone-v1 模型。这里先打印提示，避免静默丢参数。
            print(
                f"[BailianTTS] voice_prompt_path={voice_prompt_path} 暂未启用 voice clone，"
                f"将使用默认音色 {self.voice}"
            )

        text = (text or "").strip()
        if not text:
            raise BailianTTSError("synthesize() 收到空文本")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        chunks = self._split_text(text, self._MAX_CHARS_PER_CALL)
        all_bytes = bytearray()
        for idx, chunk in enumerate(chunks, start=1):
            print(
                f"[BailianTTS] 合成第 {idx}/{len(chunks)} 段，长度 {len(chunk)} 字"
            )
            audio_bytes = self._call_once(chunk)
            all_bytes.extend(audio_bytes)

        if not all_bytes:
            raise BailianTTSError("Bailian TTS 返回空音频")

        with open(output_path, "wb") as f:
            f.write(all_bytes)

        # 粗略估算时长：中文 ~5 字/秒，英文 ~3 词/秒；够前端展示用，不准也不影响 mux
        approx_duration = max(1.0, len(text) / 5.0)

        return {
            "audio_path": str(output_path),
            "duration": approx_duration,
            "model": self.model,
            "voice": self.voice,
            "bytes": len(all_bytes),
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _call_once(self, text: str, max_retry: int = 2) -> bytes:
        last_err: Optional[Exception] = None
        for attempt in range(1, max_retry + 2):  # 共尝试 max_retry+1 次
            try:
                synthesizer = SpeechSynthesizer(
                    model=self.model,
                    voice=self.voice,
                )
                audio = synthesizer.call(text)
                if audio is None:
                    raise BailianTTSError(
                        f"SpeechSynthesizer.call 返回 None，"
                        f"model={self.model} voice={self.voice}"
                    )
                if not isinstance(audio, (bytes, bytearray)):
                    raise BailianTTSError(
                        f"SpeechSynthesizer.call 返回非字节类型: {type(audio).__name__}"
                    )
                return bytes(audio)
            except Exception as e:  # 网络/限流等可重试
                last_err = e
                if attempt <= max_retry:
                    sleep_s = 1.5 * attempt
                    print(
                        f"[BailianTTS] 第 {attempt} 次失败({type(e).__name__}: {e})，"
                        f"{sleep_s:.1f}s 后重试"
                    )
                    time.sleep(sleep_s)
                else:
                    break
        raise BailianTTSError(f"Bailian TTS 多次重试仍失败: {last_err}")

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        """按句号/问号/感叹号/换行切分；保证每段 <= max_chars。"""
        if len(text) <= max_chars:
            return [text]

        # 先按强标点 + 换行切句
        sentences = re.split(r"(?<=[。！？!?\n])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[str] = []
        buf = ""
        for s in sentences:
            # 单句已经超长——硬切
            while len(s) > max_chars:
                chunks.append(s[:max_chars])
                s = s[max_chars:]
            if len(buf) + len(s) <= max_chars:
                buf += s
            else:
                if buf:
                    chunks.append(buf)
                buf = s
        if buf:
            chunks.append(buf)
        return chunks
