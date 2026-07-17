@echo off
rem BTC agent v1 intel alerts - scheduled task wrapper (every 30 min, alerts-only to avoid spam).
rem Keep this file pure ASCII. Logs under %USERPROFILE%\.btc_agent\logs\scheduler.
cd /d C:\Users\admin\Desktop\btc\btc_agent
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
set LOGDIR=%USERPROFILE%\.btc_agent\logs\scheduler
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo ===== intel run %DATE% %TIME% ===== >> "%LOGDIR%\intel.log"
.venv\Scripts\python.exe -m btc_agent.intel --asset BTC --alerts-only >> "%LOGDIR%\intel.log" 2>&1
if errorlevel 1 (
  echo [FAIL] exit %ERRORLEVEL% at %DATE% %TIME% >> "%LOGDIR%\intel.log"
  .venv\Scripts\python.exe -c "from btc_agent.intel.push import FeishuSink; FeishuSink().send('[ALERT] btc_agent intel FAILED (nonzero exit). Check %%USERPROFILE%%/.btc_agent/logs/scheduler/intel.log')" >> "%LOGDIR%\intel.log" 2>&1
  exit /b 1
)
exit /b 0
