"""
JD Price Monitor — FastAPI 后端
供 Electron 浮窗调用，WebSocket 推送实时日志/进度。
"""
import sys
import os
import json
import asyncio
import threading
import logging
import subprocess
from pathlib import Path
from typing import Optional

# ── 路径设置：找到项目根目录 ──────────────────────────────────────────────────
# server.py 在 electron-app/backend/，项目根在上两级
_HERE = Path(__file__).resolve().parent
_APP_DIR = _HERE.parent          # electron-app/
_PROJECT_ROOT = _APP_DIR.parent  # jd-price-monitor/

# 支持打包后的路径（extraResources 里）
# 打包后结构：
#   resources/backend/server.py         ← _HERE
#   resources/python-scripts/           ← 项目脚本（main.py / src/ 等）
#   resources/python/                   ← 内嵌 Python
if not (_PROJECT_ROOT / "config.yaml").exists():
    # 尝试打包后的 python-scripts 目录
    _pkg_scripts = _HERE.parent / "python-scripts"  # resources/python-scripts
    if (_pkg_scripts / "config.yaml").exists():
        _PROJECT_ROOT = _pkg_scripts
    else:
        # 旧兜底路径
        _resources = Path(os.environ.get("ELECTRON_RESOURCES_PATH", "")) / "resources" / "project"
        if (_resources / "config.yaml").exists():
            _PROJECT_ROOT = _resources

sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

# AI Agent（模块级 import，失败时给出明确错误而非 500 HTML）
try:
    from src.ai_agent import run_agent_stream as _run_agent_stream
    _AI_IMPORT_ERROR = None
except Exception as _e:
    _run_agent_stream = None  # type: ignore
    _AI_IMPORT_ERROR = str(_e)

app = FastAPI(title="JD Price Monitor API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── WebSocket 广播管理 ────────────────────────────────────────────────────────
_ws_clients: list[WebSocket] = []
_log_buffer: list[str] = []  # 保留最近 200 条，新客户端连接时补发
MAX_LOG_BUFFER = 200


async def _broadcast(msg: str, level: str = "info"):
    entry = json.dumps({"type": "log", "level": level, "msg": msg})
    _log_buffer.append(entry)
    if len(_log_buffer) > MAX_LOG_BUFFER:
        _log_buffer.pop(0)
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(entry)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


def sync_log(msg: str, level: str = "info"):
    """在同步线程里安全地广播日志"""
    entry = json.dumps({"type": "log", "level": level, "msg": msg})
    _log_buffer.append(entry)
    if len(_log_buffer) > MAX_LOG_BUFFER:
        _log_buffer.pop(0)
    # 通过事件循环调度
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _broadcast(msg, level), loop
            )
    except Exception:
        pass


# ── 重定向 logging 到 WebSocket ───────────────────────────────────────────────
class WSLogHandler(logging.Handler):
    def emit(self, record):
        level = "error" if record.levelno >= logging.ERROR else \
                "warn" if record.levelno >= logging.WARNING else "info"
        sync_log(self.format(record), level)


_ws_handler = WSLogHandler()
_ws_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(_ws_handler)
logging.getLogger().setLevel(logging.INFO)

# ── 循环巡检状态 ──────────────────────────────────────────────────────────────
_loop_thread: Optional[threading.Thread] = None
_loop_stop_event = threading.Event()
_loop_running = False


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    # 补发历史日志
    for entry in _log_buffer[-50:]:
        try:
            await websocket.send_text(entry)
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()  # 保持连接
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ── 配置 API ──────────────────────────────────────────────────────────────────
@app.get("/api/config")
def get_config():
    try:
        from src.config import reload_config
        return reload_config()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/config")
async def save_config_api(request_body: dict):
    try:
        from src.config import save_config
        save_config(request_body)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── 导出 API ──────────────────────────────────────────────────────────────────
_export_running = False


@app.post("/api/export")
async def start_export():
    global _export_running
    if _export_running:
        return {"ok": False, "msg": "导出任务已在运行"}

    def _run():
        global _export_running
        _export_running = True
        try:
            sync_log("▶ 开始导出全店商品价格...", "info")
            from src.config import reload_config
            from src.sku_fetcher import fetch_sku_list
            from src.excel_writer import write_price_excel
            from pathlib import Path as _Path

            cfg = reload_config()
            excel_to_desktop = cfg["output"].get("excel_to_desktop", True)
            if excel_to_desktop:
                out_dir = _Path.home() / "Desktop"
            else:
                out_dir = _PROJECT_ROOT / cfg["output"].get("data_dir", "data")

            sku_list = fetch_sku_list()
            if not sku_list:
                sync_log("⚠️  未抓取到任何商品，请检查 bb-browser daemon 和 Chrome 登录状态", "warn")
                return

            sync_log(f"✅ 抓取完成，共 {len(sku_list)} 个 SKU", "info")
            out_file = write_price_excel(sku_list, out_dir)
            sync_log(f"📄 Excel 已导出：{out_file}", "info")

            # 通知前端导出完成
            entry = json.dumps({"type": "export_done", "file": out_file, "count": len(sku_list)})
            _log_buffer.append(entry)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for ws in _ws_clients:
                    asyncio.run_coroutine_threadsafe(ws.send_text(entry), loop)
        except Exception as e:
            sync_log(f"❌ 导出失败：{e}", "error")
        finally:
            _export_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"ok": True}


@app.get("/api/export/status")
def export_status():
    return {"running": _export_running}


# ── 单次巡检 API ──────────────────────────────────────────────────────────────
_check_running = False


@app.post("/api/check")
async def start_check():
    global _check_running
    if _check_running:
        return {"ok": False, "msg": "巡检已在运行"}

    def _run():
        global _check_running
        _check_running = True
        try:
            sync_log("▶ 开始破价巡检...", "info")
            from src.config import reload_config
            from src.sku_fetcher import fetch_sku_list
            from src.checker import check_violations
            from src.dingtalk import send_alert
            from src.storage import save_results, cleanup_old_files
            import time

            start = time.time()
            sku_list = fetch_sku_list()
            if not sku_list:
                sync_log("⚠️  未抓取到任何商品", "warn")
                return

            violated = check_violations(sku_list)
            elapsed = time.time() - start
            if violated:
                sync_log(f"⚠️  发现 {len(violated)} 个破价 SKU！", "warn")
                send_alert(violated)
            else:
                sync_log(f"✅ 未发现破价，共 {len(sku_list)} 个 SKU，耗时 {elapsed:.1f}s", "info")

            save_results(sku_list, violated)
            cleanup_old_files()

            entry = json.dumps({
                "type": "check_done",
                "total": len(sku_list),
                "violated": len(violated),
                "elapsed": round(elapsed, 1)
            })
            _log_buffer.append(entry)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for ws in _ws_clients:
                    asyncio.run_coroutine_threadsafe(ws.send_text(entry), loop)
        except Exception as e:
            sync_log(f"❌ 巡检失败：{e}", "error")
        finally:
            _check_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"ok": True}


# ── 循环巡检 API ──────────────────────────────────────────────────────────────
@app.post("/api/loop/start")
async def loop_start():
    global _loop_thread, _loop_running, _loop_stop_event
    if _loop_running:
        return {"ok": False, "msg": "循环巡检已在运行"}

    _loop_stop_event.clear()
    _loop_running = True

    def _run():
        global _loop_running
        try:
            from src.config import reload_config
            from src.sku_fetcher import fetch_sku_list
            from src.checker import check_violations
            from src.dingtalk import send_alert
            from src.storage import save_results, cleanup_old_files
            from src.excel_writer import write_price_excel
            from pathlib import Path as _Path
            import time

            cfg = reload_config()
            interval = cfg["monitor"]["interval_minutes"] * 60
            sync_log(f"🔁 循环巡检已启动，每 {cfg['monitor']['interval_minutes']} 分钟一次", "info")

            while not _loop_stop_event.is_set():
                start = time.time()
                sync_log("▶ 执行巡检...", "info")
                try:
                    sku_list = fetch_sku_list()
                    if sku_list:
                        violated = check_violations(sku_list)
                        elapsed = time.time() - start
                        if violated:
                            sync_log(f"⚠️  发现 {len(violated)} 个破价 SKU！", "warn")
                            send_alert(violated)
                        else:
                            sync_log(f"✅ 未发现破价，{len(sku_list)} 个 SKU，{elapsed:.1f}s", "info")
                        save_results(sku_list, violated)
                        cleanup_old_files()

                        # 自动导出 Excel
                        cfg2 = reload_config()
                        if cfg2["output"].get("loop_export_excel", False):
                            out_dir = _Path.home() / "Desktop" if cfg2["output"].get("excel_to_desktop", True) \
                                else _PROJECT_ROOT / cfg2["output"].get("data_dir", "data")
                            out_file = write_price_excel(sku_list, out_dir)
                            sync_log(f"📄 Excel 已导出：{out_file}", "info")
                    else:
                        sync_log("⚠️  未抓取到商品", "warn")
                except Exception as e:
                    sync_log(f"❌ 巡检出错：{e}", "error")

                cfg = reload_config()
                interval = cfg["monitor"]["interval_minutes"] * 60
                sync_log(f"⏱  等待 {cfg['monitor']['interval_minutes']} 分钟...", "info")

                entry = json.dumps({"type": "loop_tick", "next_in": interval})
                _log_buffer.append(entry)
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    for ws in _ws_clients:
                        asyncio.run_coroutine_threadsafe(ws.send_text(entry), loop)

                _loop_stop_event.wait(interval)
        finally:
            _loop_running = False
            sync_log("⏹  循环巡检已停止", "info")
            entry = json.dumps({"type": "loop_stopped"})
            _log_buffer.append(entry)

    _loop_thread = threading.Thread(target=_run, daemon=True)
    _loop_thread.start()
    return {"ok": True}


@app.post("/api/loop/stop")
async def loop_stop():
    global _loop_running
    _loop_stop_event.set()
    return {"ok": True, "msg": "已发送停止信号"}


@app.get("/api/loop/status")
def loop_status():
    return {"running": _loop_running}


# ── Cron 管理 API ─────────────────────────────────────────────────────────────
_IS_WINDOWS = os.name == "nt"


def _get_cron_lines():
    if _IS_WINDOWS:
        return None, None  # crontab 在 Windows 不可用
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if r.returncode != 0:
            return [], []
        lines = r.stdout.splitlines()
        proj = str(_PROJECT_ROOT)
        related = [i for i, l in enumerate(lines) if "main.py" in l and proj in l]
        return lines, related
    except Exception:
        return None, None


@app.get("/api/cron/list")
def cron_list():
    if _IS_WINDOWS:
        return {"tasks": [], "unsupported": True, "msg": "定时任务在 Windows 上请使用「任务计划程序」"}
    all_lines, related = _get_cron_lines()
    if all_lines is None:
        return {"error": "crontab 不可用"}
    tasks = []
    for idx in (related or []):
        line = all_lines[idx]
        parts = line.split(None, 5)
        tasks.append({
            "index": idx,
            "expr": " ".join(parts[:5]) if len(parts) >= 5 else line,
            "cmd": parts[5][:80] if len(parts) >= 6 else ""
        })
    return {"tasks": tasks}


@app.post("/api/cron/add")
async def cron_add(body: dict):
    if _IS_WINDOWS:
        return JSONResponse({"error": "定时任务在 Windows 上暂不支持，请使用系统「任务计划程序」"}, status_code=400)
    expr = body.get("expr", "")
    if len(expr.split()) != 5:
        return JSONResponse({"error": "cron 表达式需要5段"}, status_code=400)

    from src.config import reload_config
    cfg = reload_config()
    log_dir = _PROJECT_ROOT / cfg["output"].get("log_dir", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    python_bin = _find_python()
    line = (f'{expr}  cd "{_PROJECT_ROOT}" && '
            f'"{python_bin}" main.py --no-login-wait >> "{log_dir}/cron.log" 2>&1')

    all_lines, _ = _get_cron_lines()
    if all_lines is None:
        return JSONResponse({"error": "crontab 不可用"}, status_code=500)
    new_lines = all_lines + [line]
    r = subprocess.run(["crontab", "-"], input="\n".join(new_lines) + "\n",
                       capture_output=True, text=True)
    if r.returncode != 0:
        return JSONResponse({"error": r.stderr}, status_code=500)
    return {"ok": True, "line": line}


@app.delete("/api/cron/{line_index}")
async def cron_delete(line_index: int):
    if _IS_WINDOWS:
        return JSONResponse({"error": "定时任务在 Windows 上暂不支持"}, status_code=400)
    all_lines, _ = _get_cron_lines()
    if all_lines is None:
        return JSONResponse({"error": "crontab 不可用"}, status_code=500)
    if line_index < 0 or line_index >= len(all_lines):
        return JSONResponse({"error": "索引越界"}, status_code=400)
    new_lines = [l for i, l in enumerate(all_lines) if i != line_index]
    r = subprocess.run(["crontab", "-"], input="\n".join(new_lines) + "\n",
                       capture_output=True, text=True)
    if r.returncode != 0:
        return JSONResponse({"error": r.stderr}, status_code=500)
    return {"ok": True}


# ── 工具 ──────────────────────────────────────────────────────────────────────
def _find_python() -> str:
    """找到可用的 Python 解释器（优先内嵌）"""
    # 1. 内嵌 standalone python（打包后）
    # electron-builder.yml: from electron-app/resources/python → to python
    # 打包后路径：<resourcesPath>/python/bin/python3 (macOS/Linux)
    #             <resourcesPath>/python/python.exe   (Windows)
    resources = os.environ.get("ELECTRON_RESOURCES_PATH", "")
    if resources:
        win_bin  = Path(resources) / "python" / "python.exe"
        unix_bin = Path(resources) / "python" / "bin" / "python3"
        embedded = win_bin if os.name == "nt" else unix_bin
        if embedded.exists():
            return str(embedded)
    # 2. 项目 venv
    venv_py = _PROJECT_ROOT / "venv" / "bin" / "python3"
    if venv_py.exists():
        return str(venv_py)
    # 3. 系统 Python
    import shutil
    return shutil.which("python3") or shutil.which("python") or "python3"


@app.get("/api/status")
def status():
    return {
        "project_root": str(_PROJECT_ROOT),
        "python": _find_python(),
        "config_exists": (_PROJECT_ROOT / "config.yaml").exists(),
        "loop_running": _loop_running,
        "export_running": _export_running,
        "check_running": _check_running,
        "ai_ready": _run_agent_stream is not None,
        "ai_error": _AI_IMPORT_ERROR,
    }


# ── AI Agent ──────────────────────────────────────────────────────────────────
_ai_api_key: str = ""
_ai_model: str = "MiniMax-M2.5"

@app.get("/api/ai/config")
def get_ai_config():
    return {"api_key": "***" if _ai_api_key else "", "model": _ai_model, "configured": bool(_ai_api_key)}

@app.post("/api/ai/config")
async def set_ai_config(body: dict):
    global _ai_api_key, _ai_model
    if body.get("api_key"):
        _ai_api_key = body["api_key"]
    if body.get("model"):
        _ai_model = body["model"]
    return {"ok": True}

@app.post("/api/ai/chat")
async def ai_chat(body: dict):
    """流式 SSE 聊天端点"""
    # 检查 AI 模块是否加载成功
    if _AI_IMPORT_ERROR:
        return JSONResponse(
            {"error": f"AI 模块加载失败：{_AI_IMPORT_ERROR}"},
            status_code=500
        )

    api_key = body.get("api_key") or _ai_api_key
    if not api_key:
        return JSONResponse({"error": "未配置 API Key，请在设置中填写 MiniMax API Key"}, status_code=400)

    messages = body.get("messages", [])
    model = body.get("model") or _ai_model

    async def event_stream():
        try:
            async for chunk in _run_agent_stream(messages, api_key, _PROJECT_ROOT, model):
                data = json.dumps({"text": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 启动 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7788
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
