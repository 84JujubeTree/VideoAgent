import os
import sys
import tempfile
import asyncio

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

from tools.videorag._videoutil.asr import speech_to_text


def main():
    workdir = tempfile.mkdtemp(prefix="videorag_asr_")
    cache_dir = os.path.join(workdir, "_cache", "demo_video")
    os.makedirs(cache_dir, exist_ok=True)

    # 不需要真实音频内容，mock provider 下文件存在即可
    open(os.path.join(cache_dir, "seg0.wav"), "wb").close()
    open(os.path.join(cache_dir, "seg1.wav"), "wb").close()

    result = speech_to_text(
        video_name="demo_video",
        working_dir=workdir,
        segment_index2name={0: "seg0", 1: "seg1"},
        audio_output_format="wav",
    )

    print(result)


if __name__ == "__main__":
    main()