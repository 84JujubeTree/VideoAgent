import os
import sys
import subprocess
from environment.agents.base import BaseTool
from pydantic import BaseModel, Field


class SVCCoverist(BaseTool):
    """
    Application scenario: Music cover (maintaining original melody with modified lyrics and vocal timbre alteration)
    Source-to-target voice timbre cloning (conversion) for singing voice synthesis
    Subsequently, it is often necessary to call the Mixer to add background music (BGM).
    If a music video needs to be produced, the system should immediately follow up by calling the video-related functionality components.
    """
    class InputSchema(BaseTool.BaseInputSchema):
        audio_path: str = Field(
            ...,
            description="File path to vocal singing audio"
        )
        target_vocal_path: str = Field(
            ...,
            description="File path to the target vocal"
        )

    class OutputSchema(BaseModel):
        audio_path: str = Field(
            ...,
            description="File path to the synthesized audio"
        )

    def __init__(self):
        super().__init__()

    def execute(self, **kwargs):

        params = self.InputSchema(**kwargs)
        print(f"Parameters validated successfully")


        source = os.path.abspath(params.audio_path)
        target = os.path.abspath(params.target_vocal_path)

        source_name = os.path.basename(source).split(".")[0]
        target_name = os.path.basename(target).split(".")[0]

        final_song_dir = os.path.abspath(os.path.join(
            os.path.dirname(os.path.dirname(params.audio_path)),
            'final'
        ))

        mix_audio_path = os.path.join(final_song_dir, f"{source_name}_{target_name}.wav")

        print(f"Source: {source}")
        print(f"Target: {target}")

        original_dir = os.getcwd()
        original_pythonpath = os.environ.get("PYTHONPATH", "")

        try:
            # 切换到 seedvc 目录
            seedvc_dir = os.path.join("tools", "seed-vc")
            os.chdir(seedvc_dir)
            os.makedirs(final_song_dir, exist_ok=True)

            seedvc_abs_path = os.path.abspath('.')
            os.environ["PYTHONPATH"] = seedvc_abs_path


            cmd_parts = [
                sys.executable,
                "inference.py",
                "--source", source,
                "--target", target,
                "--output", final_song_dir,
                "--f0-condition", "True"
            ]

            try:
                process = subprocess.run(cmd_parts, capture_output=True, text=True, encoding='utf-8')
            except UnicodeDecodeError:
                process = subprocess.run(cmd_parts, capture_output=True, text=False)
                stdout = process.stdout.decode('utf-8', errors='replace') if process.stdout else ""
                stderr = process.stderr.decode('utf-8', errors='replace') if process.stderr else ""
                process.stdout = stdout
                process.stderr = stderr

            print(f"标准输出: {process.stdout}")
            if process.stderr:
                print(f"错误输出: {process.stderr}")

            if process.returncode == 0:
                print("命令执行成功")
                return {
                    "audio_path": mix_audio_path
                }

            else:
                print(f"命令执行失败，返回码: {process.returncode}")
                return

        except Exception as e:
            print(f"执行过程中发生错误: {e}")
            return

        finally:
            os.chdir(original_dir)
            if original_pythonpath:
                os.environ["PYTHONPATH"] = original_pythonpath
            else:
                if "PYTHONPATH" in os.environ:
                    del os.environ["PYTHONPATH"]

            print(f"已恢复工作目录: {original_dir}")