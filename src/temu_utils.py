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

    result = _run_node(["-e", node_script], timeout=timeout + 2)
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
    _run_node(["-e", node_script], timeout=5)
    if wait:
        time.sleep(wait)


def _find_ws_module() -> str:
    """返回 node_modules/ws 的父目录（即 node_modules 的父），作为 node 运行 cwd。
    打包后在 Resources/python-scripts/，开发时在 electron-app/。
    """
    # 1. 从 TEMU_SCRIPTS_DIR 推算（Electron main.js 会传这个 env）
    scripts_dir = os.environ.get("TEMU_SCRIPTS_DIR", "")
    if scripts_dir:
        candidate = os.path.join(scripts_dir, "node_modules", "ws")
        if os.path.isdir(candidate):
            return scripts_dir

    # 2. 相对于本文件位置推算（src/temu_utils.py → ../node_modules/ws）
    here = os.path.dirname(os.path.abspath(__file__))
    for base in [
        os.path.join(here, ".."),            # 开发: python-scripts/src/ → python-scripts/
        os.path.join(here, "..", ".."),      # 开发: src/ → electron-app/ (如果脚本在根)
    ]:
        candidate = os.path.join(base, "node_modules", "ws")
        if os.path.isdir(os.path.normpath(candidate)):
            return os.path.normpath(base)

    # 3. fallback: 当前工作目录
    return os.getcwd()


def _find_node() -> str:
    """找 node 可执行路径。
    优先用 TEMU_NODE_BIN（Electron 传入的 process.execPath），
    结合 ELECTRON_RUN_AS_NODE=1 可让 Electron 以纯 Node 模式运行脚本。
    """
    node_env = os.environ.get("TEMU_NODE_BIN")
    if node_env and os.path.exists(node_env):
        return node_env
    # 开发模式 fallback：系统 node
    for p in ["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"]:
        if os.path.exists(p):
            return p
    return "node"


def _run_node(args: list, cwd: str = None, timeout: int = 10, extra_env: dict = None):
    """运行 node 脚本。若 TEMU_NODE_BIN 是 Electron，自动加 ELECTRON_RUN_AS_NODE=1"""
    node_bin = _find_node()
    env = os.environ.copy()
    # 关键：如果 node 是 Electron 自身，需要 ELECTRON_RUN_AS_NODE=1
    # 同时把父进程的 ELECTRON_RUN_AS_NODE 清空（避免影响自身）
    env.pop("ELECTRON_RUN_AS_NODE", None)
    node_is_electron = any(k in node_bin.lower() for k in ["electron", "temu assistant", "temu-assistant"])
    if node_is_electron:
        env["ELECTRON_RUN_AS_NODE"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [node_bin] + args,
        capture_output=True, timeout=timeout,
        cwd=cwd or _find_ws_module(),
        env=env
    )




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


def cdp_open_new_tab(url: str, wait: float = 3.0) -> str | None:
    """通过 CDP Target.createTarget 新开 tab 并导航，返回新 tab 的 ws url"""
    node_script = f"""
const http = require('http');
const WebSocket = require('ws');

// 先获取任意一个页面 tab 的 ws url 用来发命令
http.get('http://127.0.0.1:{CDP_PORT}/json', (res) => {{
  let d = '';
  res.on('data', x => d += x);
  res.on('end', () => {{
    const tabs = JSON.parse(d);
    const tab = tabs.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
    if (!tab) {{ process.stderr.write('no page tab found'); process.exit(1); }}
    const ws = new WebSocket(tab.webSocketDebuggerUrl);
    ws.on('open', () => {{
      // 新建 tab
      ws.send(JSON.stringify({{id: 1, method: 'Target.createTarget', params: {{url: {json.dumps(url)}}}}}));
    }});
    ws.on('message', (raw) => {{
      const msg = JSON.parse(raw.toString());
      if (msg.id === 1) {{
        ws.close();
        process.stdout.write(msg.result && msg.result.targetId ? msg.result.targetId : '');
        process.exit(0);
      }}
    }});
    ws.on('error', e => {{ process.stderr.write(e.message); process.exit(1); }});
    setTimeout(() => process.exit(1), 5000);
  }});
}}).on('error', e => {{ process.stderr.write(e.message); process.exit(1); }});
"""
    result = _run_node(["-e", node_script], timeout=8)
    target_id = result.stdout.decode('utf-8', errors='replace').strip()
    if not target_id:
        return None
    time.sleep(wait)  # 等待页面加载
    # 通过 /json 找到新 tab 的 ws url
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=3) as resp:
            tabs = json.loads(resp.read())
        for tab in tabs:
            if tab.get("id") == target_id or target_id in tab.get("webSocketDebuggerUrl", ""):
                return tab.get("webSocketDebuggerUrl")
        # fallback: 找 url 匹配的
        domain = url.split('/')[2] if '//' in url else url
        for tab in tabs:
            if tab.get("type") == "page" and domain in tab.get("url", ""):
                return tab.get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None


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
