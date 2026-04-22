import subprocess
import os


from environment.agents.base import BaseTool
from pydantic import BaseModel, Field
from typing import Union, Literal, List


class AudioExtractor(BaseTool):
    """
    Audio extraction tool which can extract audio from a single video or all videos in a directory.
    """

    def __init__(self):
        super().__init__()

    class InputSchema(BaseTool.BaseInputSchema):
        video_path: str = Field(
            ...,
            description="File path to the source video or directory containing source videos"
        )

    class OutputSchema(BaseModel):
        audio_paths: Union[List[str], str] = Field(
            ...,
            description="List of file paths to the extracted audio files or a single path"
        )
        data_dir: str = Field(
            ...,
            description="Directory containing the extracted audio files"
        )

    def get_video_files(self, video_dir):
        """Get all video files from the directory"""
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}
        video_files = []

        if not os.path.exists(video_dir):
            print(f"Error: Directory {video_dir} does not exist")
            return video_files

        for filename in os.listdir(video_dir):
            file_path = os.path.join(video_dir, filename)
            if os.path.isfile(file_path):
                _, ext = os.path.splitext(filename)
                if ext.lower() in video_extensions:
                    video_files.append(file_path)

        return video_files

    def extract_audio(self, video_path):
        """Extract audio from a single video file"""
        audio_path = os.path.splitext(video_path)[0] + ".wav"

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # 覆盖已存在文件
            "-i", video_path,
            "-vn",  # 禁用视频处理
            "-acodec", "pcm_s16le",  # 16-bit PCM编码
            "-ar", "44100",  # 采样率
            "-ac", "2",  # 立体声
            "-loglevel", "error",  # 仅显示错误信息
            audio_path
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"Audio extracted to: {audio_path}")
            return audio_path

        except subprocess.CalledProcessError as e:
            print(f"Conversion failed for {video_path}: {e}")
            return None
        except FileNotFoundError:
            print("Error: FFmpeg not found. Please install FFmpeg and add it to the system PATH")
            return None

    def execute(self, **kwargs):
        params = self.InputSchema(**kwargs)
        print(f"Parameters validated successfully")

        if os.path.isfile(params.video_path):
            audio_path = self.extract_audio(params.video_path)
            return {
                "audio_paths": audio_path if audio_path else [],
                "data_dir": os.path.dirname(params.video_path) if audio_path else ""
            }
        else:
            # 处理目录下所有视频文件
            video_dir = params.video_path
            audio_paths = self.extract_all_audio(video_dir)

            return {
                "audio_paths": audio_paths,
                "data_dir": video_dir if audio_paths else ""
            }

    def extract_all_audio(self, video_dir):
        """Extract audio from all videos in the directory"""
        video_files = self.get_video_files(video_dir)

        if not video_files:
            print(f"No video files found in directory: {video_dir}")
            return []

        audio_paths = []
        successful_extractions = 0

        print(f"Found {len(video_files)} video files. Starting extraction...")

        for video_file in video_files:
            print(f"Processing: {os.path.basename(video_file)}")
            audio_path = self.extract_audio(video_file)

            if audio_path:
                audio_paths.append(audio_path)
                successful_extractions += 1

        print(f"Extraction completed. {successful_extractions}/{len(video_files)} files processed successfully.")
        return audio_paths