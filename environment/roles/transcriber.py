import os
import subprocess
import sys
import threading
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from environment.agents.base import BaseTool


class Transcriber(BaseTool):
    """
    Video transcription tool that iteratively transcribes audio files in a directory.
    Transcription results will also be saved in the same directory.
    """

    class InputSchema(BaseTool.BaseInputSchema):
        data_dir: str = Field(
            ...,
            description="Directory of audio files to be transcribed"
        )

    class OutputSchema(BaseModel):
        status: str = Field(
            ...,
            description="Execution status (success/error)"
        )

    def __init__(self):
        super().__init__()

    def _read_output(self, pipe):
        """Realtime subprocess output reading"""
        try:
            for line in iter(pipe.readline, b''):
                if line:
                    decoded_line = line.decode('utf-8', errors='replace').strip()
                    print(f"[FAP] {decoded_line}")
        finally:
            pipe.close()

    def execute(self, **kwargs):
        """
        Execute audio transcription
        Parameter example:
        {
            "data_dir": "/path/to/audio_files"
        }
        """
        try:
            # 1. Parameter validation
            params = self.InputSchema(**kwargs)
            print(f"Parameters validated successfully")

            # 2. Path preprocessing
            data_dir = self._process_path(params.data_dir)
            print(f"Working directory: {data_dir}")

            # 3. Execute processing
            result = self._run_processing(data_dir)

            # Return dictionary instead of OutputSchema instance
            return result

        except Exception as e:
            print(e)
            # Return dictionary instead of OutputSchema instance
            return {
                "status": "error"
            }

    def _process_path(self, input_path: str) -> Path:
        """Path preprocessing"""
        path = Path(input_path)

        if not path.exists():
            raise ValueError(f"Path does not exist: {input_path}")

        if not path.is_dir():
            raise ValueError(f"Expected a directory path: {input_path}")

        return path.resolve()

    def _run_processing(self, audio_dir: Path) -> dict:
        """Execute actual transcription logic"""
        cmd = [
            "fap",
            "transcribe",
            "--model-type",
            "funasr",
            "--recursive",
            str(audio_dir)
        ]

        print(f"Executing command: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1
        )

        stdout_thread = threading.Thread(
            target=self._read_output,
            args=(process.stdout,)
        )
        stderr_thread = threading.Thread(
            target=self._read_output,
            args=(process.stderr,)
        )

        stdout_thread.start()
        stderr_thread.start()

        return_code = process.wait()
        stdout_thread.join()
        stderr_thread.join()

        if return_code == 0:
            return {
                "status": "success"
            }
        else:
            raise RuntimeError(
                f"Transcription error (code: {return_code})\n"
            )