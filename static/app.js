/* =========================================================
   AscendFlow VideoMaker — frontend logic (CapCut layout)
   ========================================================= */

(() => {
    "use strict";

    // ---------------- DOM ----------------
    const apiKeyInput   = document.getElementById("apiKey");
    const settingsBtn   = document.getElementById("settingsBtn");
    const settingsPop   = document.getElementById("settingsPopover");
    const exportBtn     = document.getElementById("exportBtn");
    const projectName   = document.getElementById("projectName");

    const railItems     = document.querySelectorAll(".rail-item");
    const panelTabs     = document.querySelectorAll(".panel-tab");
    const placeholderTitle = document.getElementById("placeholderTitle");

    const fileInput     = document.getElementById("file");
    const uploadBtn     = document.getElementById("uploadBtn");
    const canvasUpload  = document.getElementById("canvasUpload");
    const styleCards    = document.querySelectorAll(".style-card");
    const generateBtn   = document.getElementById("generateBtn");
    const assetList     = document.getElementById("assetList");

    const canvasFrame   = document.getElementById("canvasFrame");
    const canvasEmpty   = document.getElementById("canvasEmpty");
    const canvasProc    = document.getElementById("canvasProcessing");
    const canvasError   = document.getElementById("canvasError");
    const canvasDrop    = document.getElementById("canvasDropmask");
    const previewVideo  = document.getElementById("previewVideo");

    const procLabel     = document.getElementById("procLabel");
    const procPercent   = document.getElementById("procPercent");
    const errorMessage  = document.getElementById("errorMessage");
    const retryBtn      = document.getElementById("retryBtn");

    const tlPlay        = document.getElementById("tlPlay");
    const tlTime        = document.getElementById("tlTime");
    const taskIdLabel   = document.getElementById("taskIdLabel");

    const resultDrawer  = document.getElementById("resultDrawer");
    const transcriptPre = document.getElementById("transcriptPre");
    const scriptPre     = document.getElementById("scriptPre");

    const pipelineSteps = document.querySelectorAll(".pl-step");

    // ---------------- 状态 ----------------
    let selectedStyle = "standup";
    let selectedFile  = null;
    let pollTimer     = null;
    let currentTaskId = null;
    let lastResultUrl = null;

    // 后端 stage → 前端 6 步流水线 + 中文文案
    // 进度区间：0-10 接收, 10-25 预处理, 25-55 识别, 55-75 改写, 75-90 配音, 90-100 合成
    const STEPS = [
        { id: "upload",    name: "接收",       start: 0,  end: 10  },
        { id: "prepare",   name: "预处理",     start: 10, end: 25  },
        { id: "recognize", name: "识别原声",   start: 25, end: 55  },
        { id: "rewrite",   name: "AI 改写",    start: 55, end: 75  },
        { id: "voice",     name: "合成配音",   start: 75, end: 90  },
        { id: "merge",     name: "合成视频",   start: 90, end: 100 },
    ];

    const STAGE_TO_LABEL = {
        queued:        "排队中…",
        uploaded:      "已接收文件",
        probe:         "检查视频音轨",
        extract_audio: "提取原始音频",
        asr:           "AI 正在识别原声",
        llm:           "AI 正在改写脚本",
        tts:           "合成全新配音",
        mux:           "合成最终视频",
        done:          "已完成",
    };

    const TAB_NAMES = {
        media:      "媒体",
        template:   "模板",
        element:    "元素",
        audio:      "音频",
        text:       "文字",
        caption:    "字幕",
        transcript: "转录",
        effect:     "特效",
        transition: "转场",
        filter:     "滤镜",
    };

    // ---------------- API Key 持久化 ----------------
    try {
        apiKeyInput.value = localStorage.getItem("videoagent_api_key") || "";
        apiKeyInput.addEventListener("input", () => {
            localStorage.setItem("videoagent_api_key", apiKeyInput.value);
        });
    } catch (e) { /* localStorage 不可用就算了 */ }

    function authHeaders() {
        const k = (apiKeyInput.value || "").trim();
        return k ? { "X-API-Key": k } : {};
    }

    // 设置 popover 开关
    settingsBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        settingsPop.hidden = !settingsPop.hidden;
        if (!settingsPop.hidden) apiKeyInput.focus();
    });
    document.addEventListener("click", (e) => {
        if (!settingsPop.hidden &&
            !settingsPop.contains(e.target) &&
            e.target !== settingsBtn &&
            !settingsBtn.contains(e.target)) {
            settingsPop.hidden = true;
        }
    });

    // ---------------- Tab 切换 ----------------
    railItems.forEach((btn) => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.tab;
            railItems.forEach((b) => b.classList.toggle("active", b === btn));
            const isMedia = tab === "media";
            panelTabs.forEach((p) => {
                p.hidden = (p.dataset.tab !== (isMedia ? "media" : "placeholder"));
            });
            if (!isMedia) {
                placeholderTitle.textContent = `「${TAB_NAMES[tab] || tab}」敬请期待`;
            }
        });
    });

    // ---------------- 风格卡 ----------------
    styleCards.forEach((card) => {
        card.addEventListener("click", () => {
            styleCards.forEach((c) => c.classList.toggle("selected", c === card));
            selectedStyle = card.dataset.style;
        });
    });

    // ---------------- 文件选择 / 拖放 ----------------
    function pickFile() { fileInput.click(); }
    uploadBtn.addEventListener("click", pickFile);
    canvasUpload.addEventListener("click", pickFile);

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) setFile(e.target.files[0]);
    });

    function setFile(file) {
        selectedFile = file;
        if (!file) {
            renderAssets();
            generateBtn.disabled = true;
            return;
        }
        renderAssets();
        generateBtn.disabled = false;

        // 在画布预览源视频
        try {
            const url = URL.createObjectURL(file);
            previewVideo.src = url;
            previewVideo.hidden = false;
            canvasEmpty.hidden = true;
            canvasError.hidden = true;
        } catch (_) { /* ignore */ }

        // 项目名用文件名（去后缀）
        const name = file.name.replace(/\.[^.]+$/, "");
        if (name) projectName.textContent = name.length > 24 ? name.slice(0, 24) + "…" : name;
    }

    function renderAssets() {
        if (!selectedFile) {
            assetList.innerHTML = `
                <div class="asset-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 5a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5z"></path></svg>
                    <div class="asset-empty-text">目前还没有任何内容</div>
                    <div class="asset-empty-hint">将文件拖到这里或点击上方上传</div>
                </div>`;
            return;
        }
        assetList.innerHTML = `
            <div class="asset-item">
                <div class="asset-thumb">▶</div>
                <div class="asset-info">
                    <div class="asset-name">${escapeHtml(selectedFile.name)}</div>
                    <div class="asset-meta">${formatBytes(selectedFile.size)} · 视频</div>
                </div>
            </div>`;
    }

    function formatBytes(bytes) {
        if (!Number.isFinite(bytes)) return "";
        const u = ["B", "KB", "MB", "GB"];
        let i = 0, v = bytes;
        while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
        return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
        })[c]);
    }

    // 全画布拖放（在画布上松手时上传）
    let dragDepth = 0;
    canvasFrame.addEventListener("dragenter", (e) => {
        e.preventDefault(); e.stopPropagation();
        dragDepth++;
        canvasDrop.hidden = false;
    });
    canvasFrame.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); });
    canvasFrame.addEventListener("dragleave", (e) => {
        e.preventDefault(); e.stopPropagation();
        dragDepth = Math.max(0, dragDepth - 1);
        if (dragDepth === 0) canvasDrop.hidden = true;
    });
    canvasFrame.addEventListener("drop", (e) => {
        e.preventDefault(); e.stopPropagation();
        dragDepth = 0;
        canvasDrop.hidden = true;
        const f = e.dataTransfer?.files?.[0];
        if (f) setFile(f);
    });

    // ---------------- 进度可视化 ----------------
    function fillOf(step, progress) {
        if (progress <= step.start) return 0;
        if (progress >= step.end)   return 100;
        return ((progress - step.start) / (step.end - step.start)) * 100;
    }

    function applyProgress(stage, progress) {
        const pct = Math.max(0, Math.min(100, Math.round(progress || 0)));
        procPercent.textContent = pct + "%";
        procLabel.textContent = STAGE_TO_LABEL[stage] || (stage || "处理中…");

        // 找到当前活跃步骤
        let activeIdx = -1;
        for (let i = 0; i < STEPS.length; i++) {
            if (pct >= STEPS[i].start && pct < STEPS[i].end) { activeIdx = i; break; }
        }
        if (pct >= 100) activeIdx = STEPS.length;  // 全部 done

        STEPS.forEach((s, i) => {
            const li = pipelineSteps[i];
            const fill = li.querySelector(".pl-fill");
            li.classList.remove("active", "done");
            if (i < activeIdx) {
                li.classList.add("done");
                fill.style.width = "100%";
            } else if (i === activeIdx && pct < 100) {
                li.classList.add("active");
                fill.style.width = fillOf(s, pct) + "%";
            } else if (pct >= 100) {
                li.classList.add("done");
                fill.style.width = "100%";
            } else {
                fill.style.width = "0%";
            }
        });
    }

    // ---------------- 提交 ----------------
    generateBtn.addEventListener("click", submitTask);

    async function submitTask() {
        if (!selectedFile) return;

        // 重置 UI
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        canvasError.hidden = true;
        canvasEmpty.hidden = true;
        previewVideo.hidden = true;
        canvasProc.hidden = false;
        resultDrawer.hidden = true;
        exportBtn.disabled = true;
        applyProgress("queued", 0);
        generateBtn.disabled = true;
        taskIdLabel.textContent = "";

        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("style", selectedStyle);

        try {
            const resp = await fetch("/generate/from_video", {
                method: "POST",
                headers: authHeaders(),
                body: formData,
            });
            let data = {};
            try { data = await resp.json(); } catch (_) {}

            if (resp.status === 401) {
                showError("访问令牌无效或缺失，请点击右上角齿轮设置。");
                return;
            }
            if (resp.status === 429) {
                showError(data.detail || "请求过于频繁，请稍后再试。");
                return;
            }
            if (!resp.ok || !data.task_id) {
                showError(data.detail || `提交失败 (HTTP ${resp.status})`);
                return;
            }

            currentTaskId = data.task_id;
            taskIdLabel.textContent = `task ${data.task_id.slice(0, 8)}…`;

            pollTask(data.task_id);
            pollTimer = setInterval(() => pollTask(data.task_id), 2000);
        } catch (err) {
            showError(
                "网络异常：" + err +
                "（后端可能没在运行；新开标签页访问 /health 验证）"
            );
        }
    }

    async function pollTask(taskId) {
        try {
            const resp = await fetch(`/task/${taskId}`);
            const data = await resp.json();

            if (!resp.ok) {
                stopPolling();
                showError(data.detail || "任务查询失败");
                return;
            }

            applyProgress(data.stage, data.progress);

            if (data.status === "succeeded") {
                stopPolling();
                applyProgress("done", 100);
                showResult(data.result || {});
            } else if (data.status === "failed") {
                stopPolling();
                showError(data.error || "处理失败");
            }
        } catch (err) {
            // 网络抖动不立即终止，下次心跳再试
            console.warn("poll error:", err);
        }
    }

    function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        generateBtn.disabled = !selectedFile;
    }

    function showError(msg) {
        canvasProc.hidden = true;
        canvasError.hidden = false;
        previewVideo.hidden = true;
        errorMessage.textContent = msg || "未知错误";
        generateBtn.disabled = !selectedFile;
    }

    function showResult(result) {
        canvasProc.hidden = true;
        canvasError.hidden = true;

        if (result.output_video_url) {
            previewVideo.src = result.output_video_url;
            previewVideo.hidden = false;
            lastResultUrl = result.output_video_url;
            exportBtn.disabled = false;
        }

        transcriptPre.textContent = result.transcript || "（无内容）";
        scriptPre.textContent = result.script || "（无内容）";
        resultDrawer.hidden = false;
    }

    // ---------------- 顶栏导出 ----------------
    exportBtn.addEventListener("click", () => {
        if (!lastResultUrl) return;
        const a = document.createElement("a");
        a.href = lastResultUrl;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        a.remove();
    });

    // ---------------- 时间轴预览控件 ----------------
    tlPlay.addEventListener("click", () => {
        if (previewVideo.hidden) return;
        if (previewVideo.paused) previewVideo.play();
        else previewVideo.pause();
    });

    previewVideo.addEventListener("loadedmetadata", () => {
        tlTime.textContent = `00:00 / ${formatTime(previewVideo.duration)}`;
    });
    previewVideo.addEventListener("timeupdate", () => {
        tlTime.textContent =
            `${formatTime(previewVideo.currentTime)} / ${formatTime(previewVideo.duration)}`;
    });

    function formatTime(sec) {
        if (!Number.isFinite(sec)) return "00:00";
        const m = Math.floor(sec / 60).toString().padStart(2, "0");
        const s = Math.floor(sec % 60).toString().padStart(2, "0");
        return `${m}:${s}`;
    }

    // ---------------- 重试 ----------------
    retryBtn.addEventListener("click", () => {
        canvasError.hidden = true;
        if (selectedFile) {
            previewVideo.hidden = false;
        } else {
            canvasEmpty.hidden = false;
        }
    });
})();
