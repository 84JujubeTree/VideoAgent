import os
import sys
import wave
import struct
import importlib.util
import tempfile

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

module_path = r"D:\VSCode Projects\VideoAgent-main\environment\roles\stand_up\stand_up_synth.py"

spec = importlib.util.spec_from_file_location("standup_mod", module_path)
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
    workdir = tempfile.mkdtemp(prefix="stand_up_test_")

    target_vocal_dir = os.path.join(workdir, "target")
    reaction_dir = os.path.join(workdir, "reaction")

    make_silent_wav(os.path.join(target_vocal_dir, "natural.wav"))
    make_silent_wav(os.path.join(reaction_dir, "laughter.wav"))
    make_silent_wav(os.path.join(reaction_dir, "cheers.wav"))

    script = """标题行
主持人：今天我讲个段子。[Laughter]
主持人：谢谢大家。[Cheers]
"""

    synth = mod.StandUpSynth()
    result = synth.execute(
        script=script,
        target_vocal_dir=target_vocal_dir,
        reaction_dir=reaction_dir,
    )

    print("result =", result)


if __name__ == "__main__":
    main()