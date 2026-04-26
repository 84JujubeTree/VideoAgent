#
# VideoAgent MVP runtime image
# 只包含 app.py + providers/，不含 tools/ 下的本地大模型
#
# build:  docker build -t videoagent:latest .
# run:    docker run --rm -p 8000:8000 --env-file .env -v ${PWD}/tmp_videos:/app/tmp_videos videoagent:latest
#
# 国内构建建议先在 Docker Desktop -> Settings -> Docker Engine 配置 registry-mirrors，
# 见项目根 README 或当前对话说明。
#

# 可通过 --build-arg PYTHON_IMAGE=... 切换基础镜像
ARG PYTHON_IMAGE=python:3.10-slim-bookworm
FROM ${PYTHON_IMAGE}

# ---------- 系统依赖 ----------
# ffmpeg 包含 ffmpeg + ffprobe 两个二进制；ca-certificates 走 https 必备
#
# 国内默认换阿里云 Debian 源（bookworm 用 deb822 格式的 .sources 文件）。
# 在境外/已配代理时可关闭：--build-arg APT_MIRROR=
# 候选镜像（任选其一覆盖）：
#   mirrors.tuna.tsinghua.edu.cn  （清华，最稳定，默认）
#   mirrors.ustc.edu.cn           （中科大）
#   mirrors.aliyun.com            （阿里云，偶发 403）
#   mirrors.163.com               （网易）
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
RUN set -eux; \
    if [ -n "$APT_MIRROR" ] && [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i \
            -e "s|deb.debian.org|${APT_MIRROR}|g" \
            -e "s|security.debian.org|${APT_MIRROR}|g" \
            /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python 依赖 ----------
# 先单独 COPY requirements，利用 docker layer cache：requirements 不变时不重装
# 国内默认走清华源；如已配置全局代理 / 在境外构建，可 --build-arg PIP_INDEX_URL=...
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements-runtime.txt

# ---------- 应用代码 ----------
# 显式只拷需要的：千万别 COPY . .，根目录有几 GB 的 tools/
COPY app.py        /app/app.py
COPY providers/    /app/providers/
COPY static/       /app/static/

# ---------- 运行时目录 ----------
RUN mkdir -p /app/tmp_videos
VOLUME ["/app/tmp_videos"]

# ---------- 非 root 用户 ----------
RUN useradd -m -u 1001 appuser \
 && chown -R appuser:appuser /app
USER appuser

# ---------- 环境变量 ----------
# DASHSCOPE_API_KEY / BAILIAN_* 等通过 --env-file .env 注入，不写进镜像
ENV HOST=0.0.0.0 \
    PORT=8000 \
    UVICORN_RELOAD=0 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

EXPOSE 8000

# ---------- 健康检查 ----------
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

# ---------- 启动 ----------
# 直接走 uvicorn，比 python app.py 更标准，方便后续加 --workers / --proxy-headers
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
