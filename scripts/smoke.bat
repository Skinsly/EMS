@echo off
setlocal

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

set "PYTHON_EXE=%ROOT_DIR%\tools\python312\python.exe"
set "NODE_DIR=%ROOT_DIR%\tools\node22"
set "NPM_CMD=%NODE_DIR%\npm.cmd"

echo ========================================
echo EMS smoke script
echo Root: %ROOT_DIR%
echo ========================================

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Python not found: %PYTHON_EXE%
  exit /b 1
)

if not exist "%NPM_CMD%" (
  echo [ERROR] npm not found: %NPM_CMD%
  exit /b 1
)

echo.
echo [1/3] Backend smoke flow test...
pushd "%ROOT_DIR%\backend" >nul
"%PYTHON_EXE%" -m pytest tests/test_smoke_flow.py -q
if errorlevel 1 (
  echo [FAIL] Backend smoke flow test failed.
  popd >nul
  exit /b 1
)
popd >nul
echo [OK] Backend smoke flow test passed.

echo.
echo [2/3] Backend health smoke test...
pushd "%ROOT_DIR%\backend" >nul
"%PYTHON_EXE%" -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); r=c.get('/healthz'); raise SystemExit(0 if r.status_code==200 else 1)"
if errorlevel 1 (
  echo [FAIL] Backend health smoke test failed.
  popd >nul
  exit /b 1
)
popd >nul
echo [OK] Backend health smoke test passed.

echo.
echo [3/3] Frontend build smoke...
pushd "%ROOT_DIR%\frontend" >nul
set "PATH=%NODE_DIR%;%PATH%"
call "%NPM_CMD%" run build
if errorlevel 1 (
  echo [FAIL] Frontend build smoke failed.
  popd >nul
  exit /b 1
)
popd >nul
echo [OK] Frontend build smoke passed.

echo.
echo ========================================
echo SMOKE SUCCESS
echo ========================================
exit /b 0
