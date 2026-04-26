import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv
from dashscope import Generation  # DashScope LLM

from providers.bailian_asr_provider import BailianASRProvider
from providers.bailian_tts_provider import BailianTTSProvider

load_dotenv()

app = FastAPI(title="VideoAgent MVP with Provider")

# ------------------------
# 路径 / 静态资源
# ------------------------
BASE_DIR = Path("tmp_videos")
BASE_DIR.mkdir(exist_ok=True)

# 把 tmp_videos 通过 /files 暴露出去，前端可以直接 <video src="/files/..."> 播放
app.mount("/files", StaticFiles(directory=str(BASE_DIR)), name="files")

# 前端静态资源（HTML/CSS/JS 拆出来的目录），改前端不用重启 Python
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ------------------------
# 简易内存任务表（重启即清空，单进程使用）
# 生产建议换 Redis / 数据库
# ------------------------
TASKS: Dict[str, Dict[str, Any]] = {}
TASKS_LOCK = threading.Lock()


def _new_task() -> str:
    task_id = str(uuid.uuid4())
    with TASKS_LOCK:
        TASKS[task_id] = {
            "task_id": task_id,
            "status": "pending",       # pending | running | succeeded | failed
            "progress": 0,             # 0~100
            "stage": "queued",         # 当前阶段
            "created_at": time.time(),
            "updated_at": time.time(),
            "error": None,
            "result": None,
        }
    return task_id


def _update_task(task_id: str, **patch: Any) -> None:
    with TASKS_LOCK:
        if task_id not in TASKS:
            return
        TASKS[task_id].update(patch)
        TASKS[task_id]["updated_at"] = time.time()


def _get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with TASKS_LOCK:
        return TASKS.get(task_id)


# ------------------------
# 鉴权：X-API-Key 头
#   API_KEYS 留空 = 鉴权关闭（仅本地 dev，启动时会有大写警告）
#   API_KEYS=key1,key2,key3 = 任一匹配即放行
# ------------------------
API_KEYS = {
    k.strip()
    for k in os.getenv("API_KEYS", "").split(",")
    if k.strip()
}
AUTH_DISABLED = not API_KEYS

if AUTH_DISABLED:
    print(
        "\n" + "!" * 78 +
        "\n[WARN] API_KEYS 未设置，/generate 与 /tasks 当前对外完全开放。"
        "\n       公网部署前请在 .env 里配置 API_KEYS=k1,k2,k3，否则 DashScope "
        "\n       配额可能会被滥用刷爆账单。"
        "\n" + "!" * 78 + "\n"
    )


def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """FastAPI 依赖：校验 X-API-Key 头。AUTH_DISABLED 时直接放行。"""
    if AUTH_DISABLED:
        return
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail="missing or invalid X-API-Key header",
        )


# ------------------------
# 限流：滑动窗口，按客户端 IP
#   过去 RATE_LIMIT_WINDOW_SEC 秒内最多 RATE_LIMIT_MAX 次
#   RATE_LIMIT_MAX <= 0 视为关闭
# ------------------------
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "3600"))

_RATE_BUCKETS: Dict[str, Deque[float]] = defaultdict(deque)
_RATE_LOCK = threading.Lock()


def _client_ip(request: Request) -> str:
    """取客户端真实 IP；uvicorn 已 --proxy-headers，X-Forwarded-For 第一跳可信。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    if RATE_LIMIT_MAX <= 0:
        return
    ip = _client_ip(request)
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SEC
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[ip]
        # 清掉窗口外的旧记录
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_MAX:
            retry_after = max(1, int(bucket[0] + RATE_LIMIT_WINDOW_SEC - now) + 1)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"rate limit exceeded: {RATE_LIMIT_MAX} requests per "
                    f"{RATE_LIMIT_WINDOW_SEC}s; retry after {retry_after}s"
                ),
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


# ------------------------
# 首页 UI（轮询任务版本）
# ------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    """直接返回 static/index.html。改前端不用重启 Python，刷新浏览器即可。"""
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(
            status_code=500,
            detail="static/index.html 缺失，请确认前端文件已部署",
        )
    return FileResponse(str(index_path), media_type="text/html; charset=utf-8")


# ------------------------
# 工具函数：定位 ffmpeg / ffprobe 可执行文件
# 顺序：环境变量 FFMPEG_BINARY / FFPROBE_BINARY > PATH > 兄弟目录 > 报清晰错误
# ------------------------
def _resolve_ffmpeg() -> str:
    explicit = os.getenv("FFMPEG_BINARY", "").strip().strip('"')
    if explicit:
        if Path(explicit).exists():
            return explicit
        raise RuntimeError(
            f"FFMPEG_BINARY={explicit} 指向的文件不存在，请检查 .env 配置。"
        )
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError(
        "未找到 ffmpeg，请安装后再试。Windows 推荐：\n"
        "  1) winget install Gyan.FFmpeg   # 或 choco install ffmpeg / scoop install ffmpeg\n"
        "  2) 重开 PowerShell，使 PATH 生效\n"
        "  3) 也可以下载 ffmpeg.exe 后在 .env 里设置 FFMPEG_BINARY=C:\\path\\to\\ffmpeg.exe"
    )


def _resolve_ffprobe() -> str:
    explicit = os.getenv("FFPROBE_BINARY", "").strip().strip('"')
    if explicit:
        if Path(explicit).exists():
            return explicit
        raise RuntimeError(
            f"FFPROBE_BINARY={explicit} 指向的文件不存在，请检查 .env 配置。"
        )
    found = shutil.which("ffprobe")
    if found:
        return found
    # ffprobe 一般跟 ffmpeg 在同目录，兜底找一下
    try:
        ffmpeg = _resolve_ffmpeg()
        sibling_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        sibling = Path(ffmpeg).with_name(sibling_name)
        if sibling.exists():
            return str(sibling)
    except RuntimeError:
        pass
    raise RuntimeError(
        "未找到 ffprobe（一般跟 ffmpeg 同目录）。请确认 ffmpeg 安装完整，"
        "或在 .env 里设置 FFPROBE_BINARY=...绝对路径。"
    )


# ------------------------
# 工具函数：体检视频音轨
# ------------------------
def probe_audio_stream(video_path: Path) -> dict:
    """返回 {has_audio, audio_codec, sample_rate, duration_sec}"""
    ffprobe = _resolve_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "error",
         "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,sample_rate,duration:format=duration",
         "-of", "json",
         str(video_path)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe 失败: {result.stderr.decode('utf-8', errors='replace')}"
        )

    info = json.loads(result.stdout.decode("utf-8") or "{}")
    streams = info.get("streams") or []
    has_audio = bool(streams)
    audio_codec = streams[0].get("codec_name") if streams else None
    sample_rate = streams[0].get("sample_rate") if streams else None

    duration = None
    if streams and streams[0].get("duration"):
        try:
            duration = float(streams[0]["duration"])
        except (TypeError, ValueError):
            pass
    if duration is None:
        fmt_dur = (info.get("format") or {}).get("duration")
        if fmt_dur:
            try:
                duration = float(fmt_dur)
            except (TypeError, ValueError):
                pass

    return {
        "has_audio": has_audio,
        "audio_codec": audio_codec,
        "sample_rate": sample_rate,
        "duration_sec": duration,
    }


def measure_mean_loudness_db(audio_path: Path) -> float:
    """用 ffmpeg volumedetect 测平均音量；解析失败返回 -91（视为静音）"""
    ffmpeg = _resolve_ffmpeg()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats",
         "-i", str(audio_path),
         "-vn", "-sn", "-dn",
         "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
    if m:
        return float(m.group(1))
    return -91.0


# ------------------------
# 工具函数：视频提取音频
# ------------------------
def extract_audio(video_path: Path, output_dir: Path) -> Path:
    ffmpeg = _resolve_ffmpeg()
    audio_path = output_dir / (video_path.stem + ".wav")
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(video_path),
         "-ar", "16000", "-ac", "1", str(audio_path)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 提取音频失败: {result.stderr.decode('utf-8', errors='replace')}"
        )
    return audio_path


# ------------------------
# 工具函数：LLM 生成脚本
# ------------------------
def generate_script(transcript: str, style: str) -> str:
    """调用 DashScope LLM 根据转写文本生成新脚本"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    model = os.getenv("BAILIAN_LLM_MODEL", "qwen-plus")

    style_prompts = {
        "standup": "请将以下内容改写为单口喜剧风格的脱口秀脚本，语气轻松幽默：",
        "crosstalk": "请将以下内容改写为相声风格的对话脚本，加入捧哏与逗哏的互动：",
        "highlight": "请将以下内容提炼为精华摘要，突出最核心的观点：",
    }
    prompt_prefix = style_prompts.get(style, "请将以下内容改写：")

    response = Generation.call(
        api_key=api_key,
        model=model,
        prompt=f"{prompt_prefix}\n\n{transcript}",
    )

    if response.status_code != 200:
        raise RuntimeError(f"LLM 调用失败: {response.message}")

    return response.output.text


# ------------------------
# 后台任务：完整 pipeline
# ------------------------
def _run_pipeline(task_id: str, video_path: Path, workdir: Path, style: str, filename: str) -> None:
    try:
        # 0) 体检：源视频是否有音轨
        _update_task(task_id, status="running", stage="probe", progress=5)
        probe = probe_audio_stream(video_path)
        if not probe["has_audio"]:
            raise RuntimeError(
                "源视频没有检测到音轨，无法做语音识别。请上传带人声的视频，"
                "或先用其它工具补一段配音再上传。"
            )
        if probe.get("duration_sec") is not None and probe["duration_sec"] < 0.5:
            raise RuntimeError(
                f"视频时长仅 {probe['duration_sec']:.2f}s，太短无法识别"
            )

        _update_task(task_id, stage="extract_audio", progress=10)
        audio_path = extract_audio(video_path, workdir)

        # 1) 体检：抽出来的音频是否近似静音
        mean_db = measure_mean_loudness_db(audio_path)
        if mean_db <= -50.0:
            raise RuntimeError(
                f"提取出来的音频平均音量 {mean_db:.1f} dB，接近静音。"
                "可能原因：原视频音轨为空 / 全是背景音乐 / DRM 保护。"
                "请确认视频带有清晰人声后重试。"
            )
        _update_task(task_id, stage="asr", progress=25, audio_mean_db=mean_db)

        asr_provider = BailianASRProvider()
        transcript_result = asr_provider.transcribe(audio_path, lang="zh")
        transcript = transcript_result["text"]
        segments = transcript_result["segments"]

        if not transcript.strip():
            raise RuntimeError(
                "ASR 返回空文本（音频中没有识别到任何语音内容）。"
                "请确认视频里有清晰的中文人声。"
            )

        _update_task(task_id, stage="llm", progress=55)
        rewritten_script = generate_script(transcript, style)

        _update_task(task_id, stage="tts", progress=75)
        tts_provider = BailianTTSProvider()
        tts_output_path = workdir / "tts_output.mp3"
        tts_result = tts_provider.synthesize(
            text=rewritten_script,
            output_path=tts_output_path,
        )

        _update_task(task_id, stage="mux", progress=90)
        ffmpeg = _resolve_ffmpeg()
        output_video = workdir / f"{Path(filename).stem}_output.mp4"
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", str(video_path),
             "-i", str(tts_output_path),
             "-map", "0:v:0",
             "-map", "1:a:0",
             "-c:v", "copy",
             "-c:a", "aac",
             "-shortest",
             str(output_video)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg 合成视频失败: {result.stderr.decode('utf-8', errors='replace')}"
            )

        # 通过 /files 静态目录暴露
        rel_workdir = workdir.relative_to(BASE_DIR).as_posix()
        output_video_url = f"/files/{rel_workdir}/{output_video.name}"
        tts_audio_url = f"/files/{rel_workdir}/{tts_output_path.name}"

        # 顺手写一份 metadata.json 方便下载
        metadata = {
            "style": style,
            "transcript": transcript,
            "segments": segments,
            "script": rewritten_script,
            "tts_audio": tts_result.get("audio_path", str(tts_output_path)),
            "output_video": str(output_video),
        }
        metadata_path = workdir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        metadata_url = f"/files/{rel_workdir}/{metadata_path.name}"

        _update_task(
            task_id,
            status="succeeded",
            stage="done",
            progress=100,
            result={
                "style": style,
                "transcript": transcript,
                "segments": segments,
                "script": rewritten_script,
                "output_video_url": output_video_url,
                "tts_audio_url": tts_audio_url,
                "metadata_url": metadata_url,
            },
        )

    except Exception as e:
        traceback.print_exc()
        _update_task(
            task_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            progress=100,
        )


# ------------------------
# 提交任务接口（立即返回 task_id）
# ------------------------
@app.post("/generate/from_video")
async def generate_from_video(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    style: str = Form("standup"),
    _auth: None = Depends(require_api_key),
):
    check_rate_limit(request)
    try:
        task_id = _new_task()
        workdir = BASE_DIR / task_id
        workdir.mkdir(parents=True, exist_ok=True)

        # 保存上传视频（同步保存以确保后台任务能读到文件）
        filename = Path(file.filename or "input.mp4").name
        video_path = workdir / filename
        with open(video_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        _update_task(task_id, stage="uploaded", progress=5)

        # 丢到后台跑
        background_tasks.add_task(_run_pipeline, task_id, video_path, workdir, style, filename)

        return JSONResponse(
            {"task_id": task_id, "status": "pending", "poll_url": f"/task/{task_id}"},
            status_code=202,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ------------------------
# 任务状态查询
# ------------------------
@app.get("/task/{task_id}")
async def get_task(task_id: str):
    task = _get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task 不存在或已被回收")
    return task


@app.get("/tasks")
async def list_tasks(
    limit: int = 50,
    _auth: None = Depends(require_api_key),
):
    """全任务列表会泄露其它用户提交的内容，强制鉴权。"""
    with TASKS_LOCK:
        items = sorted(TASKS.values(), key=lambda t: t["created_at"], reverse=True)
    return {"tasks": items[:limit]}


# ------------------------
# 下载 / 健康检查
# ------------------------
@app.get("/download")
async def download_video(video_path: str):
    path = Path(video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return FileResponse(str(path), media_type="video/mp4", filename=path.name)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload_flag = os.getenv("UVICORN_RELOAD", "0") == "1"

    uvicorn.run("app:app", host=host, port=port, reload=reload_flag)
