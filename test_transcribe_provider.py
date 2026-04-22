from pathlib import Path
import importlib.util
import sys

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

module_path = r"D:\VSCode Projects\VideoAgent-main\tools\audio-preprocess\fish_audio_preprocess\utils\transcribe.py"

spec = importlib.util.spec_from_file_location("transcribe_mod", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

result = mod.batch_transcribe(
    files=[Path("demo.wav")],
    model_size="mock",
    model_type="whisper",
    lang="zh",
    pos=0,
    compute_type="int8",
    batch_size=1,
)

print(result)