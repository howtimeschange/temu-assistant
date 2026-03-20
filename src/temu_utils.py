"""
Temu 运营助手 — 公共工具函数
bb-browser + CDP 操作封装
"""
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime

CDP_PORT = os.environ.get("TEMU_CDP_PORT", "9222")


# ── CDP WebSocket 直连工具 ─────────────────────────────────────────────────────

def get_tab_ws_url(domain: str) -> str | None:
    """通过 CDP HTTP API 找到包含指定域名的 tab 的 WebSocket URL"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=3) as resp:
            tabs = json.loads(resp.read())
        for tab in tabs:
            if tab.get("type") == "page" and domain in tab.get("url", ""):
                return tab.get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None


def cdp_eval(ws_url: str, expression: str, timeout: int = 30):
    """通过 CDP WebSocket 执行 JS 表达式，返回结果值"""
    import threading
    import json as _json

    try:
        import websocket as _ws_lib
    except ImportError:
        _ws_lib = None

    # 使用 node 内置 ws 模块执行（因为 Python 没有 websocket-client）
    node_script = f"""
const WebSocket = require('ws');
const ws = new WebSocket({_json.dumps(ws_url)});
let done = false;
ws.on('open', () => {{
  ws.send(JSON.stringify({{id: 1, method: 'Runtime.evaluate', params: {{
    expression: {_json.dumps(expression)},
    returnByValue: true,
    awaitPromise: true
  }}}}));
}});
ws.on('message', (raw) => {{
  if (done) return;
  const msg = JSON.parse(raw.toString());
  if (msg.id === 1) {{
    done = true;
    const r = msg.result && msg.result.result;
    if (r && r.value !== undefined) process.stdout.write(JSON.stringify(r.value));
    else if (r && r.type === 'boolean') process.stdout.write(String(r.value));
    else process.stdout.write(JSON.stringify(null));
    ws.close();
    process.exit(0);
  }}
}});
ws.on('error', e => {{ process.stderr.write(e.message); process.exit(1); }});
setTimeout(() => {{ process.exit(1); }}, {timeout * 1000});
"""

    # 找 node 可执行路径
    node_bin = _find_node()
    # 找 ws 模块路径
    ws_path = _find_ws_module()

    result = subprocess.run(
        [node_bin, "--input-type=module" if False else "-e", node_script],
        capture_output=True, text=False, timeout=timeout + 2,
        cwd=ws_path
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout.decode('utf-8', errors='replace').strip())
    except Exception:
        return result.stdout.decode('utf-8', errors='replace').strip()


def cdp_navigate(ws_url: str, url: str, wait: float = 0.5):
    """通过 CDP 导航到指定 URL"""
    node_script = f"""
const WebSocket = require('ws');
const ws = new WebSocket({json.dumps(ws_url)});
ws.on('open', () => {{
  ws.send(JSON.stringify({{id: 1, method: 'Page.navigate', params: {{url: {json.dumps(url)}}}}}));
  setTimeout(() => {{ ws.close(); process.exit(0); }}, 500);
}});
ws.on('error', e => {{ process.exit(1); }});
setTimeout(() => process.exit(0), 3000);
"""
    node_bin = _find_node()
    ws_path = _find_ws_module()
    subprocess.run([node_bin, "-e", node_script], capture_output=True, timeout=5, cwd=ws_path)
    if wait:
        time.sleep(wait)


def _find_node() -> str:
    """找 node 可执行路径"""
    node_env = os.environ.get("ELECTRON_NODE_BIN")
    if node_env and os.path.exists(node_env):
        return node_env
    for p in ["/opt/homebrew/bin/node", "/usr/local/bin/node", "node"]:
        if p == "node" or os.path.exists(p):
            return p
    return "node"


def _find_ws_module() -> str:
    """找包含 ws 模块的 node_modules 目录"""
    # Electron app 目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # 优先用 electron-app/node_modules
    electron_app = os.path.join(project_root, "electron-app")
    if os.path.exists(os.path.join(electron_app, "node_modules", "ws")):
        return electron_app

    # 回退到项目根
    if os.path.exists(os.path.join(project_root, "node_modules", "ws")):
        return project_root

    return project_root


def bb(args, timeout=20):
    """运行 bb-browser 命令，返回 CompletedProcess"""
    cmd = ["bb-browser"] + args + ["--port", CDP_PORT]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def bb_json(args, timeout=30) -> dict:
    """运行 bb-browser 命令，解析 JSON 输出"""
    r = bb(args + ["--json"], timeout=timeout)
    if r.returncode != 0:
        err_msg = (r.stderr.strip() or r.stdout.strip() or "bb-browser error")[:300]
        return {"error": err_msg, "items": []}
    try:
        out = r.stdout.strip()
        start = out.find('{')
        if start > 0:
            out = out[start:]
        return json.loads(out)
    except Exception as e:
        return {"error": str(e), "raw": r.stdout[:300]}


def get_tab_by_domain(domain: str) -> str | None:
    """找到包含指定域名的 tab index"""
    r = bb(["tab", "list"])
    for line in r.stdout.splitlines():
        if domain in line:
            m = re.search(r'\[(\d+)\]', line)
            if m:
                return m.group(1)
    return None


def open_new_tab(url: str) -> str | None:
    """新开 tab 并导航到 url，返回 tab index"""
    bb(["tab", "new", url])
    time.sleep(2)
    return get_tab_by_domain(url.split('/')[2])


def navigate_tab(tab: str, url: str):
    """切换到 tab 并导航"""
    bb(["tab", tab])
    bb(["eval", f"location.href='{url}'", "--tab", tab])


def wait_for_selector(tab: str, selector: str, max_wait=25) -> bool:
    """等待某个 CSS 选择器出现，返回是否成功"""
    js = f"document.querySelectorAll('{selector}').length"
    for _ in range(max_wait):
        time.sleep(1)
        r = bb(["eval", js, "--tab", tab], timeout=5)
        try:
            if int(r.stdout.strip()) > 0:
                return True
        except Exception:
            pass
    return False


def click_next_page(tab: str) -> bool:
    """点击下一页按钮，返回是否成功点击"""
    js = """
    (function() {
      const selectors = [
        '.ant-pagination-next:not(.ant-pagination-disabled) button',
        '.ant-pagination-next:not(.ant-pagination-disabled)',
        '[aria-label="Next"]:not([disabled])',
        '[class*="next-page"]:not([disabled])'
      ];
      for (const sel of selectors) {
        const btn = document.querySelector(sel);
        if (btn && !btn.disabled && btn.offsetParent !== null) {
          btn.click();
          return true;
        }
      }
      return false;
    })()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    return r.stdout.strip().lower() == 'true'


def close_popup(tab: str) -> dict:
    """尝试关闭弹窗，返回 {closed: bool, still_visible: bool}"""
    js = """
    (function() {
      const selectors = [
        '.ant-modal-close',
        '[class*="modal"] button[class*="close"]',
        '[aria-label="Close"]',
        '[aria-label="close"]',
        '.ant-modal-footer .ant-btn-primary',
        '[class*="dialog"] button:last-child'
      ];
      for (const sel of selectors) {
        const btn = document.querySelector(sel);
        if (btn && btn.offsetParent !== null) {
          btn.click();
          return 'closed';
        }
      }
      const modal = document.querySelector('.ant-modal-wrap:not([style*="display: none"])');
      return modal ? 'still_visible' : 'none';
    })()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    result = r.stdout.strip().strip('"').strip("'")
    return {"closed": result == "closed", "still_visible": result == "still_visible"}


def install_temu_adapters():
    """将 temu adapters 安装到 bb-browser sites 目录"""
    # __file__ 是 src/temu_utils.py，adapters/ 在项目根（上一级）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adapter_src = os.path.join(project_root, "adapters", "temu")
    bb_root = os.path.expanduser("~/.bb-browser/sites/temu")
    os.makedirs(bb_root, exist_ok=True)
    for fname in os.listdir(adapter_src):
        if fname.endswith(".js"):
            src = os.path.join(adapter_src, fname)
            dst = os.path.join(bb_root, fname)
            with open(src) as f:
                content = f.read()
            with open(dst, "w") as f:
                f.write(content)


def desktop_path(filename: str) -> str:
    """返回桌面文件路径"""
    return os.path.join(os.path.expanduser("~/Desktop"), filename)


def timestamped_name(prefix: str, ext: str = "xlsx") -> str:
    """生成带时间戳的文件名"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{ext}"
