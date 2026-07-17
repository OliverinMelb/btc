@echo off
rem BTC agent v2 daily decision card - scheduled task wrapper.
rem Keep this file pure ASCII (cmd codepage pitfalls). Logs under %USERPROFILE%\.btc_agent\logs\scheduler.
cd /d C:\Users\admin\Desktop\btc\btc_agent
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
set LOGDIR=%USERPROFILE%\.btc_agent\logs\scheduler
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo ===== daily run %DATE% %TIME% ===== >> "%LOGDIR%\daily.log"
.venv\Scripts\python.exe -m btc_agent.daily --asset BTC >> "%LOGDIR%\daily.log" 2>&1
if errorlevel 1 (
  echo [FAIL] exit %ERRORLEVEL% at %DATE% %TIME% >> "%LOGDIR%\daily.log"
  .venv\Scripts\python.exe -c "from btc_agent.intel.push import FeishuSink; FeishuSink().send('[ALERT] btc_agent daily FAILED (nonzero exit). Check %%USERPROFILE%%/.btc_agent/logs/scheduler/daily.log')" >> "%LOGDIR%\daily.log" 2>&1
  exit /b 1
)
exit /b 0
