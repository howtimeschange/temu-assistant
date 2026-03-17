"""
轻量 AI Agent — 接入 MiniMax M2.5（兼容 OpenAI 格式）
工具集：读日志、读配置、写配置、检查状态、读巡检结果
"""
import json
import os
import glob
from pathlib import Path
from typing import AsyncGenerator

import httpx

# ── 配置 ──────────────────────────────────────────────────────────────────────
MINIMAX_API_BASE = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M2.5"

SYSTEM_PROMPT = """你是「京东价格监控助手」，内嵌在 JD Price Monitor 桌面应用中。

你的职责：
- 帮助用户排查问题（Chrome 未启动、bb-browser 报错、抓取失败等）
- 解释巡检结果和破价数据
- 指导用户配置（钉钉 webhook、巡检间隔、价格阈值等）
- 回答关于应用使用的任何问题

你有以下工具可以调用来获取实时信息：
- read_recent_logs：读取最近的运行日志
- read_config：读取当前配置文件
- update_config：更新配置项
- read_latest_results：读取最新巡检结果
- get_app_status：获取应用运行状态

回答要简洁、实用，遇到问题直接给出解决步骤。"""

# ── 工具定义 ──────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_recent_logs",
            "description": "读取应用最近的运行日志，用于排查错误",
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {"type": "integer", "description": "读取行数，默认50", "default": 50}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_config",
            "description": "读取当前 config.yaml 配置内容",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_config",
            "description": "更新配置项，例如修改巡检间隔、钉钉 webhook、价格阈值等",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "要更新的配置键值对，支持点号路径如 monitor.interval_minutes"
                    }
                },
                "required": ["updates"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_latest_results",
            "description": "读取最新一次巡检结果，包括 SKU 列表和破价商品",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_app_status",
            "description": "获取应用当前状态：Chrome CDP 是否就绪、Python 路径、配置路径等",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


# ── 工具执行 ──────────────────────────────────────────────────────────────────
def _execute_tool(name: str, args: dict, project_root: Path) -> str:
    try:
        if name == "read_recent_logs":
            lines = args.get("lines", 50)
            log_dir = project_root / "logs"
            log_files = sorted(glob.glob(str(log_dir / "*.log")), reverse=True)
            if not log_files:
                return "暂无日志文件"
            with open(log_files[0], encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return "".join(all_lines[-lines:]) or "日志为空"

        elif name == "read_config":
            cfg_file = project_root / "config.yaml"
            if not cfg_file.exists():
                return "config.yaml 不存在"
            return cfg_file.read_text(encoding="utf-8")

        elif name == "update_config":
            import yaml
            cfg_file = project_root / "config.yaml"
            with open(cfg_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            updates = args.get("updates", {})
            for key_path, value in updates.items():
                keys = key_path.split(".")
                d = cfg
                for k in keys[:-1]:
                    d = d.setdefault(k, {})
                d[keys[-1]] = value
            with open(cfg_file, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
            return f"配置已更新：{updates}"

        elif name == "read_latest_results":
            data_dir = project_root / "data"
            result_files = sorted(glob.glob(str(data_dir / "results_*.json")), reverse=True)
            if not result_files:
                return "暂无巡检结果"
            with open(result_files[0], encoding="utf-8") as f:
                data = json.load(f)
            total = len(data.get("sku_list", []))
            violated = data.get("violated", [])
            summary = f"最新巡检（{result_files[0].split('/')[-1]}）：共 {total} 个 SKU，破价 {len(violated)} 个\n"
            if violated:
                for v in violated[:10]:
                    summary += f"  [{v.get('sku_id','')}] {v.get('name','')[:20]} 吊牌¥{v.get('original_price','?')} → 前台¥{v.get('current_price','?')}\n"
            return summary

        elif name == "get_app_status":
            import shutil
            status = {
                "config_exists": (project_root / "config.yaml").exists(),
                "python": shutil.which("python3") or "not found",
                "bb_browser": shutil.which("bb-browser") or os.path.expanduser("~/.npm-global/bin/bb-browser"),
                "log_dir": str(project_root / "logs"),
                "data_dir": str(project_root / "data"),
            }
            return json.dumps(status, ensure_ascii=False, indent=2)

        else:
            return f"未知工具：{name}"
    except Exception as e:
        return f"工具执行出错：{e}"


# ── Agent 主循环（流式） ───────────────────────────────────────────────────────
async def run_agent_stream(
    messages: list,
    api_key: str,
    project_root: Path,
    model: str = DEFAULT_MODEL,
) -> AsyncGenerator[str, None]:
    """流式 Agent 循环，yield SSE 文本片段"""

    history = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    max_steps = 8

    async with httpx.AsyncClient(timeout=60) as client:
        for step in range(max_steps):
            # 调用 LLM
            payload = {
                "model": model,
                "messages": history,
                "tools": TOOLS,
                "stream": True,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            full_content = ""
            tool_calls_raw = {}

            async with client.stream(
                "POST",
                f"{MINIMAX_API_BASE}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"\n❌ API 错误 {resp.status_code}: {body.decode()[:200]}\n"
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})

                    # 文本内容流式输出
                    if delta.get("content"):
                        full_content += delta["content"]
                        yield delta["content"]

                    # 收集 tool_calls
                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_raw:
                            tool_calls_raw[idx] = {"id": tc.get("id", ""), "name": "", "args": ""}
                        if tc.get("function", {}).get("name"):
                            tool_calls_raw[idx]["name"] = tc["function"]["name"]
                        if tc.get("function", {}).get("arguments"):
                            tool_calls_raw[idx]["args"] += tc["function"]["arguments"]

            # 没有工具调用 → 任务完成
            if not tool_calls_raw:
                return

            # 有工具调用 → 执行并继续
            assistant_msg = {"role": "assistant", "content": full_content, "tool_calls": []}
            tool_results = []

            for idx, tc in tool_calls_raw.items():
                try:
                    args = json.loads(tc["args"]) if tc["args"] else {}
                except Exception:
                    args = {}

                yield f"\n\n🔧 *调用工具：{tc['name']}*\n"
                result = _execute_tool(tc["name"], args, project_root)
                yield f"```\n{result[:500]}\n```\n\n"

                assistant_msg["tool_calls"].append({
                    "id": tc["id"] or f"call_{idx}",
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["args"]}
                })
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"] or f"call_{idx}",
                    "content": result,
                })

            history.append(assistant_msg)
            history.extend(tool_results)
