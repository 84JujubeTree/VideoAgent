import os
import sys
import wave
import struct
import importlib.util
import tempfile

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

module_path = r"D:\VSCode Projects\VideoAgent-main\environment\roles\cross_talk\cross_talk_synth.py"

spec = importlib.util.spec_from_file_location("cross_talk_mod", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_silent_wav(path, duration_sec=1, sample_rate=16000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n_samples = sample_rate * duration_sec
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        silence = struct.pack("<h", 0)
        for _ in range(n_samples):
            wf.writeframesraw(silence)


def main():
    workdir = tempfile.mkdtemp(prefix="cross_talk_test_")

    # 目录结构：
    # workdir/
    #   dou/
    #     natural.wav / emphatic.wav / confused.wav
    #   peng/
    #     natural.wav / emphatic.wav / confused.wav
    dou_dir = os.path.join(workdir, "dou")
    peng_dir = os.path.join(workdir, "peng")

    for role_dir in [dou_dir, peng_dir]:
        for tone in ["natural", "emphatic", "confused"]:
            make_silent_wav(os.path.join(role_dir, f"{tone}.wav"))

    # 第一行会被代码跳过，所以故意放一个标题行
    script = """标题行
dou：今天我们来聊点有意思的。
peng：你先说说看，到底哪里有意思？
"""

    synth = mod.CrossTalkSynth()
    result = synth.execute(
        script=script,
        dou_gen_dir=dou_dir,
        peng_gen_dir=peng_dir,
    )

    print("result =", result)


if __name__ == "__main__":
    main()