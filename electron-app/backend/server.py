"""
Temu 运营助手 — FastAPI 后端
供 Electron 浮窗调用，WebSocket 推送实时日志/进度。
"""
import sys
import os
import json
import asyncio
import threading
import logging
from pathlib import Path
from typing import Optional

# ── 路径设置 ──────────────────────────────────────────────────────────────────
# server.py 在 electron-app/backend/，项目根在上两级
_HERE = Path(__file__).resolve().parent
_APP_DIR = _HERE.parent          # electron-app/
_PROJECT_ROOT = _APP_DIR.parent  # temu-assistant/

# 支持打包后路径
if not (_PROJECT_ROOT / "temu_goods_data.py").exists():
    _pkg_scripts = _HERE.parent / "python-scripts"  # resources/python-scripts
    if (_pkg_scripts / "temu_goods_data.py").exists():
        _PROJECT_ROOT = _pkg_scripts
    else:
        _resources = Path(os.environ.get("ELECTRON_RESOURCES_PATH", "")) / "python-scripts"
        if (_resources / "temu_goods_data.py").exists():
            _PROJECT_ROOT = _resources

sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Temu Assistant API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── WebSocket 广播 ────────────────────────────────────────────────────────────
_ws_clients: list[WebSocket] = []
_log_buffer: list[str] = []
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
        if ws in _ws_clients:
            _ws_clients.remove(ws)


def sync_log(msg: str, level: str = "info"):
    """在同步线程里安全地广播日志"""
    entry = json.dumps({"type": "log", "level": level, "msg": msg})
    _log_buffer.append(entry)
    if len(_log_buffer) > MAX_LOG_BUFFER:
        _log_buffer.pop(0)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(msg, level), loop)
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

# ── 任务状态 ──────────────────────────────────────────────────────────────────
_task_thread: Optional[threading.Thread] = None
_task_stop_event = threading.Event()
_task_running = False
_task_name: str = ""


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    for entry in _log_buffer[-50:]:
        try:
            await websocket.send_text(entry)
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ── 状态 API ──────────────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    return {
        "project_root": str(_PROJECT_ROOT),
        "python": _find_python(),
        "task_running": _task_running,
        "task_name": _task_name,
    }


# ── 配置 API ──────────────────────────────────────────────────────────────────
@app.get("/api/config")
def get_config():
    try:
        import yaml
        cfg_path = _PROJECT_ROOT / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/config")
async def save_config_api(body: dict):
    try:
        import yaml
        cfg_path = _PROJECT_ROOT / "config.yaml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── 任务 API ──────────────────────────────────────────────────────────────────

def _run_task_thread(task_func, task_name: str):
    """在后台线程中运行任务函数"""
    global _task_running, _task_name
    _task_running = True
    _task_name = task_name
    _task_stop_event.clear()
    try:
        sync_log(f"▶ 开始任务: {task_name}", "info")
        task_func()
        sync_log(f"✅ 任务完成: {task_name}", "info")
    except Exception as e:
        sync_log(f"❌ 任务失败 [{task_name}]: {e}", "error")
        import traceback
        sync_log(traceback.format_exc(), "error")
    finally:
        _task_running = False
        _task_name = ""
        # 通知前端任务结束
        entry = json.dumps({"type": "task_done", "name": task_name})
        _log_buffer.append(entry)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for ws in _ws_clients:
                    asyncio.run_coroutine_threadsafe(ws.send_text(entry), loop)
        except Exception:
            pass


@app.post("/api/task/goods-data")
async def task_goods_data(body: dict):
    global _task_thread
    if _task_running:
        return {"ok": False, "msg": "已有任务在运行"}

    mode = body.get("mode", "current")
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")

    def _run():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "temu_goods_data", str(_PROJECT_ROOT / "temu_goods_data.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 传递参数给 run()
            kwargs = {"mode": mode, "log_fn": sync_log}
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date
            mod.run(**kwargs)
        except Exception as e:
            sync_log(f"❌ 商品数据抓取失败: {e}", "error")
            raise

    _task_thread = threading.Thread(target=_run_task_thread, args=(_run, "商品数据"), daemon=True)
    _task_thread.start()
    return {"ok": True}


@app.post("/api/task/aftersales")
async def task_aftersales(body: dict):
    global _task_thread
    if _task_running:
        return {"ok": False, "msg": "已有任务在运行"}

    mode = body.get("mode", "current")
    regions = body.get("regions", [])

    def _run():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "temu_aftersales", str(_PROJECT_ROOT / "temu_aftersales.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            kwargs = {"mode": mode, "log_fn": sync_log}
            if regions:
                kwargs["regions"] = regions
            mod.run(**kwargs)
        except Exception as e:
            sync_log(f"❌ 售后数据抓取失败: {e}", "error")
            raise

    _task_thread = threading.Thread(target=_run_task_thread, args=(_run, "售后数据"), daemon=True)
    _task_thread.start()
    return {"ok": True}


@app.post("/api/task/reviews")
async def task_reviews(body: dict):
    global _task_thread
    if _task_running:
        return {"ok": False, "msg": "已有任务在运行"}

    shop_url = body.get("shop_url", "")
    if not shop_url:
        return JSONResponse({"error": "shop_url 不能为空"}, status_code=400)

    def _run():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "temu_reviews", str(_PROJECT_ROOT / "temu_reviews.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run(shop_url=shop_url, log_fn=sync_log)
        except Exception as e:
            sync_log(f"❌ 评价抓取失败: {e}", "error")
            raise

    _task_thread = threading.Thread(target=_run_task_thread, args=(_run, "店铺评价"), daemon=True)
    _task_thread.start()
    return {"ok": True}


@app.post("/api/task/store-items")
async def task_store_items(body: dict):
    global _task_thread
    if _task_running:
        return {"ok": False, "msg": "已有任务在运行"}

    shop_url = body.get("shop_url", "")
    if not shop_url:
        return JSONResponse({"error": "shop_url 不能为空"}, status_code=400)

    def _run():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "temu_store_items", str(_PROJECT_ROOT / "temu_store_items.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run(shop_url=shop_url, log_fn=sync_log)
        except Exception as e:
            sync_log(f"❌ 站点商品抓取失败: {e}", "error")
            raise

    _task_thread = threading.Thread(target=_run_task_thread, args=(_run, "站点商品"), daemon=True)
    _task_thread.start()
    return {"ok": True}


@app.post("/api/task/stop")
async def task_stop():
    global _task_running, _task_name
    _task_stop_event.set()
    _task_running = False
    _task_name = ""
    sync_log("⏹ 任务已停止", "warn")
    return {"ok": True}


@app.get("/api/task/status")
def task_status():
    return {"running": _task_running, "name": _task_name}


# ── 文件列表 API ──────────────────────────────────────────────────────────────
@app.get("/api/files/recent")
def files_recent():
    import stat as stat_mod
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return []
    files = []
    for f in desktop.iterdir():
        if f.name.startswith("temu_") and f.name.endswith(".xlsx"):
            st = f.stat()
            files.append({
                "name": f.name,
                "path": str(f),
                "mtime": st.st_mtime,
                "size": st.st_size,
            })
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files[:10]


# ── 工具 ──────────────────────────────────────────────────────────────────────
def _find_python() -> str:
    resources = os.environ.get("ELECTRON_RESOURCES_PATH", "")
    if resources:
        win_bin  = Path(resources) / "python" / "python.exe"
        unix_bin = Path(resources) / "python" / "bin" / "python3"
        embedded = win_bin if os.name == "nt" else unix_bin
        if embedded.exists():
            return str(embedded)
    venv_py = _PROJECT_ROOT / "venv" / "bin" / "python3"
    if venv_py.exists():
        return str(venv_py)
    import shutil
    return shutil.which("python3") or shutil.which("python") or "python3"


# ── 启动 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7788
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
