import importlib.util
import sys

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

module_path = r"D:\VSCode Projects\VideoAgent-main\tools\videorag\_videoutil\feature.py"

spec = importlib.util.spec_from_file_location("feature_mod", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

video_result = mod.encode_video_segments(["demo.mp4"], None)
query_result = mod.encode_string_query("测试文本", None)

print("video_result =", video_result)
print("query_result =", query_result)