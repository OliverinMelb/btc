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

rem Export dashboard data and push so Vercel redeploys. Failures here only warn;
rem they never flip the daily exit code (card was already delivered).
.venv\Scripts\python.exe -m btc_agent.webexport >> "%LOGDIR%\daily.log" 2>&1
cd /d C:\Users\admin\Desktop\btc
git add web/data/dashboard.json >> "%LOGDIR%\daily.log" 2>&1
git commit -m "data: daily dashboard export" >> "%LOGDIR%\daily.log" 2>&1
git push origin master >> "%LOGDIR%\daily.log" 2>&1
if errorlevel 1 (
  echo [WARN] dashboard export/push failed at %DATE% %TIME% >> "%LOGDIR%\daily.log"
)
rem Vercel CLI production deploy of web/ (GitHub auto-deploy integration not connected).
call "%APPDATA%\npm\vercel.cmd" deploy --prod --yes --cwd C:\Users\admin\Desktop\btc\web >> "%LOGDIR%\daily.log" 2>&1
if errorlevel 1 (
  echo [WARN] vercel deploy failed at %DATE% %TIME% >> "%LOGDIR%\daily.log"
)
exit /b 0
