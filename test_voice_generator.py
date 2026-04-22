import importlib.util
import sys

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

module_path = r"D:\VSCode Projects\VideoAgent-main\environment\roles\voice_generator.py"

spec = importlib.util.spec_from_file_location("voice_generator_mod", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

vg = mod.VoiceGenerator()
result = vg.execute(
    video_scene_path=r"D:\VSCode Projects\VideoAgent-main\test_scene.json",
    target_vocal_path=r"D:\VSCode Projects\VideoAgent-main\dummy_prompt.wav",
)

print(result)