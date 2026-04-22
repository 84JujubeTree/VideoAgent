import subprocess
from pydantic import BaseModel, Field
from environment.agents.base import BaseTool

class Merge(BaseTool):
    """
    Merge video and audio tracks without retrieving video clips to combine into a video; instead, directly merge the complete video and audio.
    Note the differences between Mixer (which outputs audio), VideoPreloader, VideoSearcher, and VideoEditor (which retrieves video clips to combine into a video).
    """
    class InputSchema(BaseTool.BaseInputSchema):
        video_path: str = Field(
            ...,
            description="File path to the video"
        )
        audio_path: str = Field(
            ...,
            description="File path to the audio"
        )

    class OutputSchema(BaseModel):
        video_path: str = Field(
            ...,
            description="File path to the merged video"
        )

    def execute(self, **kwargs):
        params = self.InputSchema(**kwargs)
        print(f"Parameters validated successfully")

        audio_path = params.audio_path
        video_path = params.video_path
        output_path = video_path

        try:
            cmd = [
                'ffmpeg',
                '-i', video_path,  # 输入视频
                '-i', audio_path,  # 输入音频
                '-c:v', 'libx264',  # 视频编码器
                '-preset', 'fast',  # 编码速度/质量平衡
                '-crf', '23',  # 视频质量(18-28, 越小质量越高)
                '-c:a', 'aac',  # 音频编码器
                '-b:a', '192k',  # 音频比特率
                '-map', '0:v:0',  # 选择第一个输入的视频流
                '-map', '1:a:0',  # 选择第二个输入的音频流
                '-shortest',  # 以较短的输入为准
                '-movflags', '+faststart',  # 优化网络播放
                '-y',  # 覆盖输出文件(如果存在)
                output_path
            ]
            # 运行FFmpeg命令
            subprocess.run(cmd, check=True)
            print(f"成功合并视频和音频到: {output_path}")
            return {
                "video_path": output_path
            }
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg处理失败: {e}")
            return
        except Exception as e:
            print(f"发生错误: {str(e)}")
            return