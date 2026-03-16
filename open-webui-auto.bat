@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "FRONTEND_HOST=0.0.0.0"
set "FRONTEND_PORT=5173"

set "PY_EXE=%ROOT%\tools\python312\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=D:\tools\python312\python.exe"

set "NODE_HOME=%ROOT%\tools\node22"
if not exist "%NODE_HOME%\node.exe" (
  if exist "%NODE_HOME%\node-v22.13.1-win-x64\node.exe" set "NODE_HOME=%NODE_HOME%\node-v22.13.1-win-x64"
)
if not exist "%NODE_HOME%\node.exe" if exist "D:\tools\node-v22.22.0-win-x64\node.exe" set "NODE_HOME=D:\tools\node-v22.22.0-win-x64"
set "NODE_EXE=%NODE_HOME%\node.exe"
set "NPM_CLI=%NODE_HOME%\node_modules\npm\bin\npm-cli.js"
set "NPM_CMD=%NODE_HOME%\npm.cmd"
set "VITE_CLI=%ROOT%\frontend\node_modules\vite\bin\vite.js"
set "FRONTEND_PATH=%NODE_HOME%;%ROOT%\frontend\node_modules\.bin;%PATH%"

if not exist "%PY_EXE%" (
  where py >nul 2>nul
  if %ERRORLEVEL%==0 (
    set "PY_EXE=py -3"
  ) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
      set "PY_EXE=python"
    ) else (
      echo [ERROR] Python not found. Install Python or restore tools\python312 or D:\tools\python312
      pause
      exit /b 1
    )
  )
)

set "USE_NODE_CLI=0"
if exist "%NODE_EXE%" if exist "%NPM_CLI%" set "USE_NODE_CLI=1"

if "%USE_NODE_CLI%"=="0" (
  if not exist "%NPM_CMD%" (
    where npm >nul 2>nul
    if %ERRORLEVEL%==0 (
      set "NPM_CMD=npm"
    ) else (
      echo [ERROR] Node/npm not found. Install Node.js or restore tools\node22 or D:\tools\node-v22.22.0-win-x64
      pause
      exit /b 1
    )
  )
)

if not exist "%ROOT%\frontend\node_modules\vite\bin\vite.js" (
  echo Frontend dependencies not ready. Installing...
  if "%USE_NODE_CLI%"=="1" (
    cmd /d /s /c "set PATH=%FRONTEND_PATH% && cd /d "%ROOT%\frontend" && "%NODE_EXE%" "%NPM_CLI%" install"
  ) else (
    cmd /d /s /c "set PATH=%FRONTEND_PATH% && cd /d "%ROOT%\frontend" && %NPM_CMD% install"
  )
  if errorlevel 1 (
    echo [ERROR] Frontend dependency install failed.
    echo Try manually in a normal terminal:
    echo   cd /d "%ROOT%\frontend"
    if "%USE_NODE_CLI%"=="1" (
      echo   "%NODE_EXE%" "%NPM_CLI%" install
    ) else (
      echo   %NPM_CMD% install
    )
    pause
    exit /b 1
  )
)

if not exist "%ROOT%\frontend\node_modules\vite\bin\vite.js" (
  echo [ERROR] vite is still missing after install. Frontend cannot start.
  pause
  exit /b 1
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ip=[System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) ^| Where-Object { $_.AddressFamily -eq 'InterNetwork' -and -not $_.IPAddressToString.StartsWith('127.') } ^| Select-Object -First 1 -ExpandProperty IPAddressToString; if(-not $ip){$ip='127.0.0.1'}; Write-Output $ip"`) do set "LAN_IP=%%I"

set "LOCAL_URL=http://localhost:%FRONTEND_PORT%/#/login"
set "LAN_URL=http://%LAN_IP%:%FRONTEND_PORT%/#/login"

netsh advfirewall firewall show rule name="EMS Frontend %FRONTEND_PORT%" >nul 2>nul
if errorlevel 1 (
  netsh advfirewall firewall add rule name="EMS Frontend %FRONTEND_PORT%" dir=in action=allow protocol=TCP localport=%FRONTEND_PORT% >nul 2>nul
)

start "EMS Backend" cmd /k "cd /d ""%ROOT%\backend"" && %PY_EXE% -m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"

if "%USE_NODE_CLI%"=="1" (
  if exist "%VITE_CLI%" (
    start "EMS Frontend" cmd /k "set PATH=%FRONTEND_PATH% && cd /d ""%ROOT%\frontend"" && ""%NODE_EXE%"" ""%VITE_CLI%"" --host %FRONTEND_HOST% --port %FRONTEND_PORT% --strictPort"
  ) else (
    start "EMS Frontend" cmd /k "set PATH=%FRONTEND_PATH% && cd /d ""%ROOT%\frontend"" && ""%NODE_EXE%"" ""%NPM_CLI%"" run dev -- --host %FRONTEND_HOST% --port %FRONTEND_PORT% --strictPort"
  )
) else (
  start "EMS Frontend" cmd /k "set PATH=%FRONTEND_PATH% && cd /d ""%ROOT%\frontend"" && %NPM_CMD% run dev -- --host %FRONTEND_HOST% --port %FRONTEND_PORT% --strictPort"
)

echo Waiting for frontend to boot...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(60); while((Get-Date) -lt $deadline){ try{ $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2; if($r.StatusCode -ge 200){ exit 0 } } catch {}; Start-Sleep -Milliseconds 800 }; exit 1"
if %ERRORLEVEL%==0 (
  start "" "%LOCAL_URL%"
  echo Opened (PC): %LOCAL_URL%
  echo Phone URL: %LAN_URL%
) else (
  echo [WARN] Frontend not ready in 60s. Opening page anyway...
  start "" "%LOCAL_URL%"
  echo Try on phone: %LAN_URL%
)

endlocal
