@echo off
setlocal

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

echo ========================================
echo EMS full smoke script
echo Root: %ROOT_DIR%
echo ========================================

echo.
echo [1/2] Run full verify script...
call "%ROOT_DIR%\scripts\verify.bat"
if errorlevel 1 (
  echo [FAIL] verify.bat failed.
  exit /b 1
)
echo [OK] verify.bat passed.

echo.
echo [2/2] Run full backend pytest suite...
pushd "%ROOT_DIR%\backend" >nul
"%ROOT_DIR%\tools\python312\python.exe" -m pytest tests -q
if errorlevel 1 (
  echo [FAIL] Full backend pytest failed.
  popd >nul
  exit /b 1
)
popd >nul
echo [OK] Full backend pytest passed.

echo.
echo ========================================
echo FULL SMOKE SUCCESS
echo ========================================
exit /b 0
