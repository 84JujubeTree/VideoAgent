import subprocess
from pathlib import Path
import os
import wave
import contextlib
import sys
from environment.agents.base import BaseTool
from pydantic import BaseModel, Field


class TTSInfer(BaseTool):
    """
    Application scenario: A reworded version of the original video
    Take the sliced audio clips as target voice references, then conduct Text-To-Speech synthesis using their rewritten text segments.
    """
    def __init__(self):
        super().__init__()

    class InputSchema(BaseTool.BaseInputSchema):
        audio_path: str = Field(
            ...,
            description="File path to the audio track of the video"
        )
        speech_path: str = Field(
            ...,
            description="File path to save the rewritten text"
        )

    class OutputSchema(BaseModel):
        slice_dir: str = Field(
            ...,
            description="Directory for the synthesized sliced audio"
        )

    def get_audio_duration(self, wav_file_path):
        """获取音频文件的时长（秒）"""
        try:
            with contextlib.closing(wave.open(str(wav_file_path), 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                duration = frames / float(rate)
                return duration
        except Exception as e:
            print(f"Error getting audio duration: {e}")
            return 0

    def execute(self, **kwargs):

        params = self.InputSchema(**kwargs)
        print(f"Parameters validated successfully")

        splits = []
        with open(params.speech_path, 'r', encoding='utf-8') as file:
            for line in file:
                splits.append(line.strip())

        fish_speech_path = os.path.join(os.getcwd(), "tools", "fish-speech")
        if fish_speech_path not in sys.path:
            sys.path.append(fish_speech_path)

        # Split copy text into paragraphs
        print(f"Total paragraphs: {len(splits)}")

        current_dir = os.getcwd()
        slice_dir = os.path.splitext(params.audio_path)[0]
        path = Path(slice_dir)
        new_dir_name = "derivative"
        new_dir_path = path / new_dir_name
        new_dir_path.mkdir(parents=True, exist_ok=True)

        try:
            lab_files_with_content = []
            for lab_file in sorted([f for f in path.glob("*.lab")], key=lambda x: int(x.stem)):
                with open(lab_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                lab_files_with_content.append({
                    "path": lab_file,
                    "content": content,
                    "wav_path": lab_file.with_suffix('.wav')
                })

            print(f"Total lab files: {len(lab_files_with_content)}")
            results = []

            for split_idx, split in enumerate(splits):
                if split_idx >= len(lab_files_with_content):
                    print(f"Warning: More paragraphs than lab files. Skipping paragraph {split_idx}.")
                    continue

                combined_lab_content = ""
                combined_wav_files = []
                combined_duration = 0

                lab_file_info = lab_files_with_content[split_idx]
                lab_file = lab_file_info["path"]
                wav_file = lab_file_info["wav_path"]

                combined_lab_content += lab_file_info["content"]

                combined_wav_files.append(wav_file)
                current_duration = self.get_audio_duration(wav_file)
                combined_duration += current_duration

                if combined_duration < 1:
                    additional_count = 1
                    while combined_duration < 1 and additional_count < len(lab_files_with_content):
                        next_idx = (split_idx + additional_count) % len(lab_files_with_content)

                        if next_idx == split_idx:
                            additional_count += 1
                            continue

                        add_lab_file_info = lab_files_with_content[next_idx]
                        add_wav_file = add_lab_file_info["wav_path"]
                        combined_lab_content += add_lab_file_info["content"]

                        combined_wav_files.append(add_wav_file)
                        add_duration = self.get_audio_duration(add_wav_file)
                        combined_duration += add_duration

                        additional_count += 1

                filename = lab_file.stem

                print(
                    f"Processing paragraph {split_idx + 1}/{len(splits)}, using {len(combined_wav_files)} wav files")

                if len(combined_wav_files) > 1:
                    temp_wav_path = new_dir_path / f"temp_{filename}.wav"

                    os.chdir(current_dir)

                    try:
                        import numpy as np
                        from scipy.io import wavfile

                        audio_data = []
                        sample_rate = None

                        for wav_file in combined_wav_files:
                            rate, data = wavfile.read(str(wav_file))
                            if sample_rate is None:
                                sample_rate = rate
                            elif rate != sample_rate:
                                raise ValueError("All WAV files must have the same sample rate")
                            audio_data.append(data)

                        combined_audio = np.concatenate(audio_data)

                        wavfile.write(str(temp_wav_path), sample_rate, combined_audio)

                        combined_wav_file = temp_wav_path

                    except Exception as e:
                        print(f"Failed to merge audio files: {e}")
                        combined_wav_file = combined_wav_files[0]
                else:
                    combined_wav_file = combined_wav_files[0]

                os.chdir(os.path.join(current_dir, "tools", "fish-speech"))

                cmd1 = [
                    sys.executable,
                    "fish_speech/models/vqgan/inference.py",
                    "-i", f"../../{combined_wav_file}",
                    "--checkpoint-path", "checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth",
                    "--output-path", f"../../{new_dir_path}/{filename}.wav"
                ]

                process1 = subprocess.Popen(
                    cmd1,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    bufsize=0
                )

                stdout, stderr = process1.communicate()
                print(stdout)
                print(stderr)

                if process1.returncode != 0:
                    raise Exception(f"VQGAN inference failed with return code {process1.returncode}")

                print("cmd1 complete successfully")

                print("Starting cmd2...")
                cmd2 = [
                    sys.executable,
                    "fish_speech/models/text2semantic/inference.py",
                    "--text", split,
                    "--prompt-text", combined_lab_content,
                    "--prompt-tokens", f"../../{new_dir_path}/{filename}.npy",
                    "--checkpoint-path", "checkpoints/fish-speech-1.5",
                    "--num-samples", "1"
                ]

                process2 = subprocess.Popen(
                    cmd2,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    bufsize=0
                )

                stdout, stderr = process2.communicate()
                print(stdout)
                print(stderr)

                if process2.returncode != 0:
                    raise Exception(f"Text2Semantic inference failed with return code {process2.returncode}")

                print("cmd2 complete successfully")

                print("Starting cmd3...")
                cmd3 = [
                    sys.executable,
                    "fish_speech/models/vqgan/inference.py",
                    "-i", f"temp/codes_0.npy",
                    "--checkpoint-path", "checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth",
                    "--output-path", f"../../{new_dir_path}/{filename}.wav"
                ]

                process3 = subprocess.Popen(
                    cmd3,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    bufsize=0
                )

                stdout, stderr = process3.communicate()
                print(stdout)
                print(stderr)

                if process3.returncode != 0:
                    raise Exception(f"Vqgan inference failed with return code {process3.returncode}")

                result_lab_files = [str(lab_file)]
                result_wav_files = [str(wav_file) for wav_file in combined_wav_files]

                results.append({
                    "lab_files": result_lab_files,
                    "wav_files": result_wav_files,
                    "paragraph": split,
                    "status": "success"
                })
                os.chdir(current_dir)

                # 清理临时文件
                if len(combined_wav_files) > 1 and os.path.exists(str(temp_wav_path)):
                    try:
                        os.remove(str(temp_wav_path))
                    except Exception as e:
                        print(f"Failed to remove temporary file: {e}")

            try:
                import numpy as np
                from scipy.io import wavfile

                generated_wavs = sorted(
                    [f for f in new_dir_path.glob("*.wav")],
                    key=lambda x: int(x.stem)
                )

                audio_data = []
                sample_rate = None

                for wav_file in generated_wavs:
                    rate, data = wavfile.read(str(wav_file))
                    if sample_rate is None:
                        sample_rate = rate
                    elif rate != sample_rate:
                        raise ValueError("All WAV files must have the same sample rate")
                    audio_data.append(data)

                combined_audio = np.concatenate(audio_data)

                final_output_path = new_dir_path / "final.wav"
                wavfile.write(str(final_output_path), sample_rate, combined_audio)

                print(f"Successfully merged all audio files into {final_output_path}")

                return {
                    "derivative_dir": new_dir_path
                }
            except Exception as e:
                print(f"Failed to merge audio files: {e}")
                return

        except Exception as e:
            print(f"Exception occurred: {e}")
            return