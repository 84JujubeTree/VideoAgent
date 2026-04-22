import subprocess
import sys
import threading
from pathlib import Path
from pydantic import BaseModel, Field
from environment.agents.base import BaseTool


class Separator(BaseTool):
    """
    Audio source separation tool that commonly serve as audio preprocessing.
    Video files are not supported directly. If needed, first extract the audio track from your video (using an audio extraction tool).
    """

    class InputSchema(BaseTool.BaseInputSchema):
        data_dir: str = Field(
            ...,
            description="Iteratively perform vocal separation on audio files under the directory"
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
        Execute audio source separation
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

            return self.OutputSchema(**result)

        except Exception as e:
            return self.OutputSchema(
                status="error",
            )

    def _process_path(self, input_path: str) -> Path:
        """Path preprocessing"""
        path = Path(input_path)

        if not path.exists():
            raise ValueError(f"Path does not exist: {input_path}")

        if not path.is_dir():
            raise ValueError(f"Expected a directory path: {input_path}")

        return path.resolve()

    def _run_processing(self, data_dir: Path) -> dict:
        """Execute actual processing logic"""
        cmd = [
            "fap",
            "separate",
            str(data_dir),
            str(data_dir),
            "--overwrite",
            "--recursive"
        ]

        # Filter empty arguments
        cmd = list(filter(None, cmd))
        print(f"Executing command: {' '.join(cmd)}")

        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1
        )

        # Output capture
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

        # Result handling
        if return_code == 0:
            return {
                "status": "success",
            }
        else:
            raise RuntimeError(
                f"Processing error (code: {return_code})\n"
            )