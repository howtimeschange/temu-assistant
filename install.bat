@echo off
:: =============================================================================
::  JD Price Monitor — 一键安装脚本（Windows）
::  用法：双击运行，或在终端中执行 install.bat
:: =============================================================================
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

set "PROJ_DIR=%~dp0"
:: 去掉末尾的反斜杠
if "%PROJ_DIR:~-1%"=="\" set "PROJ_DIR=%PROJ_DIR:~0,-1%"

set "VENV_DIR=%PROJ_DIR%\venv"
set "ADAPTER_DIR=%USERPROFILE%\.bb-browser\bb-sites\jd"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     JD Price Monitor — 安装程序          ║
echo  ║     京东价格监控 · 一键安装 (Windows)    ║
echo  ╚══════════════════════════════════════════╝
echo.

:: =============================================================================
:: Step 1: 检查 Python 3.9+
:: =============================================================================
echo [1/5] 检查 Python 环境...

set "PYTHON="
for %%C in (python3.12 python3.11 python3.10 python3.9 python3 python) do (
    if not defined PYTHON (
        where %%C >nul 2>&1 && (
            for /f "tokens=2 delims= " %%V in ('%%C --version 2^>^&1') do (
                set "PYVER=%%V"
            )
            echo   OK: Python !PYVER! ^(%%C^)
            set "PYTHON=%%C"
        )
    )
)

if not defined PYTHON (
    echo   ERROR: 未找到 Python 3.9+，请先安装：
    echo   https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: =============================================================================
:: Step 2: 创建虚拟环境 & 安装 Python 依赖
:: =============================================================================
echo.
echo [2/5] 安装 Python 依赖...

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   → 创建虚拟环境 ...
    %PYTHON% -m venv "%VENV_DIR%"
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

echo   → 升级 pip ...
"%VENV_PIP%" install --upgrade pip -q

echo   → 安装依赖（rich, questionary, openpyxl, pyyaml ...）...
"%VENV_PIP%" install -r "%PROJ_DIR%\requirements.txt" -q
echo   OK: Python 依赖安装完成

:: =============================================================================
:: Step 3: 检查 Node.js & 安装 bb-browser
:: =============================================================================
echo.
echo [3/5] 安装 bb-browser...

where node >nul 2>&1
if errorlevel 1 (
    echo   ERROR: 未找到 Node.js，请先安装：
    echo   https://nodejs.org/  （推荐 LTS 版本）
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('node --version') do set "NODEVER=%%V"
echo   OK: Node.js %NODEVER%

where bb-browser >nul 2>&1
if errorlevel 1 (
    echo   → 安装 bb-browser ...
    npm install -g bb-browser
) else (
    echo   → 检查 bb-browser 更新 ...
    npm install -g bb-browser
)
echo   OK: bb-browser 安装完成

echo   → 更新 bb-browser 社区 adapter 库 ...
bb-browser site update 2>nul || echo   WARN: adapter 更新失败（可忽略）

:: =============================================================================
:: Step 4: 安装 JD adapter
:: =============================================================================
echo.
echo [4/5] 安装 JD adapter...

if not exist "%ADAPTER_DIR%" mkdir "%ADAPTER_DIR%"
copy /Y "%PROJ_DIR%\adapters\jd\shop-prices.js" "%ADAPTER_DIR%\shop-prices.js" >nul
echo   OK: adapter 已复制到 %ADAPTER_DIR%\shop-prices.js

:: =============================================================================
:: Step 5: 创建启动脚本
:: =============================================================================
echo.
echo [5/5] 创建启动脚本...

:: 生成 jd-monitor.bat
set "LAUNCHER=%PROJ_DIR%\jd-monitor.bat"
(
    echo @echo off
    echo :: JD Price Monitor 启动脚本
    echo "%VENV_PYTHON%" "%PROJ_DIR%\cli.py" %%*
) > "%LAUNCHER%"
echo   OK: 启动脚本：%LAUNCHER%

:: =============================================================================
:: 完成
:: =============================================================================
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   安装完成！
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 使用前，请完成以下准备：
echo.
echo   1. 启动 bb-browser daemon（新开一个终端窗口运行）
echo      for /f %%P in ('npm root -g') do node %%P\bb-browser\dist\daemon.js
echo.
echo   2. 打开 Chrome 并启用远程调试
echo      "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
echo.
echo   3. 安装 bb-browser Chrome 扩展（仅首次）
echo      chrome://extensions/ → 开发者模式 → 加载已解压的扩展程序
echo      for /f %%P in ('npm root -g') do echo 路径：%%P\bb-browser\extension
echo.
echo   4. 在 Chrome 中打开京东并登录
echo.
echo 然后双击运行：
echo      %LAUNCHER%
echo.
echo 提示：首次运行后，可在设置菜单中配置店铺 URL、阈值、钉钉 Webhook
echo.
pause
