#!/usr/bin/env python3
"""
Temu 运营助手 — 交互式命令行
运行: python temu_cli.py
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── 依赖检查 ──────────────────────────────────────────────────────────────────
def _ensure_deps():
    required = {"rich": "rich", "questionary": "questionary", "openpyxl": "openpyxl"}
    missing = [pkg for mod, pkg in required.items() if not __import_ok(mod)]
    if missing:
        print(f"正在安装依赖: {', '.join(missing)} ...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + missing, check=True)

def __import_ok(mod):
    try: __import__(mod); return True
    except ImportError: return False

_ensure_deps()

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from rich.rule import Rule

sys.path.insert(0, os.path.dirname(__file__))

console = Console()

Q_STYLE = Style([
    ("qmark",       "fg:#FF6B35 bold"),
    ("question",    "bold"),
    ("answer",      "fg:#4ECDC4 bold"),
    ("pointer",     "fg:#FF6B35 bold"),
    ("highlighted", "fg:#FF6B35 bold"),
    ("selected",    "fg:#4ECDC4"),
    ("separator",   "fg:#6C6C6C"),
    ("instruction", "fg:#6C6C6C italic"),
])

CDP_PORT = os.environ.get("TEMU_CDP_PORT", "9222")
DEFAULT_WAIT = 40

# ── 工具 ──────────────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    banner = Text()
    banner.append("  🛍️  Temu 运营助手", style="bold #FF6B35")
    banner.append("   Powered by bb-browser + CDP", style="dim")
    console.print(Panel(banner, border_style="#FF6B35", padding=(0, 2)))
    console.print()

def ask(question, **kwargs):
    return questionary.text(question, style=Q_STYLE, **kwargs).ask()

def ask_select(question, choices, **kwargs):
    return questionary.select(question, choices=choices, style=Q_STYLE, **kwargs).ask()

def ask_confirm(question, default=True):
    return questionary.confirm(question, default=default, style=Q_STYLE).ask()

def ask_checkbox(question, choices, **kwargs):
    return questionary.checkbox(question, choices=choices, style=Q_STYLE, **kwargs).ask()

def ask_mode():
    return ask_select(
        "登录模式",
        choices=["在当前页面（使用现有登录态）", "全新页面（新开 tab 登录）"]
    )

def get_mode_key(choice: str) -> str:
    return "new" if "全新" in choice else "current"

def ask_login_wait():
    val = ask("登录等待秒数", default=str(DEFAULT_WAIT))
    try:
        return int(val)
    except Exception:
        return DEFAULT_WAIT

def ask_output(default_name: str) -> str:
    desktop = os.path.expanduser("~/Desktop")
    path = ask(
        "输出文件路径（留空=桌面）",
        default=os.path.join(desktop, default_name)
    )
    return path.strip() or os.path.join(desktop, default_name)

def print_result(path: str | None):
    console.print()
    if path:
        console.print(f"  ✅ 文件已保存: [bold cyan]{path}[/bold cyan]")
    else:
        console.print("  ⚠️  未生成文件，请检查页面状态")
    console.print()
    input("  按 Enter 返回主菜单...")

# ── 功能模块 ──────────────────────────────────────────────────────────────────

def module_goods_data():
    clear(); print_banner()
    console.print(Rule("[bold]📦 后台 · 商品数据抓取[/bold]", style="#FF6B35"))
    console.print()

    mode_choice = ask_mode()
    mode = get_mode_key(mode_choice)

    login_wait = DEFAULT_WAIT
    if mode == "new":
        login_wait = ask_login_wait()

    # 时间筛选
    use_date = ask_confirm("是否设置时间区间筛选？", default=False)
    start_date, end_date = "", ""
    if use_date:
        start_date = ask("开始日期 (YYYY-MM-DD)", default=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
        end_date   = ask("结束日期 (YYYY-MM-DD)", default=datetime.now().strftime("%Y-%m-%d"))

    from datetime import datetime as dt
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    output = ask_output(f"temu_goods_data_{ts}.xlsx")

    console.print()
    console.print(Rule(style="dim"))

    import temu_goods_data
    result = temu_goods_data.run(
        mode=mode, start_date=start_date, end_date=end_date,
        output_path=output, login_wait=login_wait,
        print_fn=lambda s: console.print(f"  {s}")
    )
    print_result(result)


def module_aftersales():
    clear(); print_banner()
    console.print(Rule("[bold]🔄 后台 · 售后数据抓取[/bold]", style="#FF6B35"))
    console.print()

    mode_choice = ask_mode()
    mode = get_mode_key(mode_choice)

    login_wait = DEFAULT_WAIT
    if mode == "new":
        login_wait = ask_login_wait()

    regions = ask_checkbox(
        "选择要抓取的地区（空格选中，Enter 确认）",
        choices=["全球", "美国", "欧区"],
        default=["全球", "美国", "欧区"]
    )
    if not regions:
        regions = ["全球"]

    from datetime import datetime as dt
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    output = ask_output(f"temu_aftersales_{ts}.xlsx")

    console.print()
    console.print(Rule(style="dim"))

    import temu_aftersales
    result = temu_aftersales.run(
        mode=mode, regions=regions, output_path=output,
        login_wait=login_wait,
        print_fn=lambda s: console.print(f"  {s}")
    )
    print_result(result)


def module_reviews():
    clear(); print_banner()
    console.print(Rule("[bold]⭐ 店铺评价抓取[/bold]", style="#FF6B35"))
    console.print()

    shop_url = ask(
        "店铺链接",
        default="https://www.temu.com/mall.html?mall_id=634418216574527"
    )
    if not shop_url.strip():
        console.print("  ⚠️  未输入链接，返回")
        time.sleep(1)
        return

    login_wait = ask_login_wait()

    from datetime import datetime as dt
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    output = ask_output(f"temu_reviews_{ts}.xlsx")

    console.print()
    console.print(Rule(style="dim"))

    import temu_reviews
    result = temu_reviews.run(
        shop_url=shop_url.strip(), output_path=output,
        login_wait=login_wait,
        print_fn=lambda s: console.print(f"  {s}")
    )
    print_result(result)


def module_store_items():
    clear(); print_banner()
    console.print(Rule("[bold]🏪 站点商品数据抓取[/bold]", style="#FF6B35"))
    console.print()

    shop_url = ask(
        "店铺链接",
        default="https://www.temu.com/mall.html?mall_id=634418216574527"
    )
    if not shop_url.strip():
        console.print("  ⚠️  未输入链接，返回")
        time.sleep(1)
        return

    login_wait = ask_login_wait()

    from datetime import datetime as dt
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    output = ask_output(f"temu_store_items_{ts}.xlsx")

    console.print()
    console.print(Rule(style="dim"))

    import temu_store_items
    result = temu_store_items.run(
        shop_url=shop_url.strip(), output_path=output,
        login_wait=login_wait,
        print_fn=lambda s: console.print(f"  {s}")
    )
    print_result(result)


def module_settings():
    clear(); print_banner()
    console.print(Rule("[bold]⚙️  设置[/bold]", style="dim"))
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("k", style="dim", width=14)
    t.add_column("v", style="cyan")
    t.add_row("CDP 端口",   CDP_PORT)
    t.add_row("登录等待",   f"{DEFAULT_WAIT}s")
    t.add_row("默认输出",   os.path.expanduser("~/Desktop"))
    console.print(t)
    console.print()

    new_port = ask("CDP 端口", default=CDP_PORT)
    os.environ["TEMU_CDP_PORT"] = new_port.strip()
    console.print(f"  ✓ CDP 端口已设为 {new_port}")
    time.sleep(1)


# ── 主菜单 ────────────────────────────────────────────────────────────────────

MENU = [
    ("📦  后台-商品数据抓取",   module_goods_data),
    ("🔄  后台-售后数据抓取",   module_aftersales),
    ("⭐  店铺评价抓取",         module_reviews),
    ("🏪  站点商品数据抓取",    module_store_items),
    ("⚙️   设置",                module_settings),
    ("❌  退出",                 None),
]


def main():
    while True:
        clear()
        print_banner()

        console.print(f"  CDP 端口 [dim]{CDP_PORT}[/dim]   bb-browser + Chrome Remote Debugging")
        console.print()

        choice = ask_select(
            "请选择功能",
            choices=[label for label, _ in MENU]
        )

        if choice is None:
            break

        for label, fn in MENU:
            if label == choice:
                if fn is None:
                    console.print("\n  👋 再见！\n")
                    sys.exit(0)
                fn()
                break


if __name__ == "__main__":
    main()
