@echo off
setlocal
title AirDash Gesture Control
color 0B

:: Move to the root directory
cd /d "%~dp0.."

:menu
cls
echo =======================================================
echo                 AirDash Gesture Control                
echo =======================================================
echo.
echo   [1] Setup Environment (Install dependencies)
echo   [2] Run AirDash
echo   [3] Exit
echo.
echo =======================================================
set /p choice="Enter your choice (1-3): "

if "%choice%"=="1" goto setup
if "%choice%"=="2" goto run
if "%choice%"=="3" goto end
echo Invalid choice. Try again.
timeout /t 2 >nul
goto menu

:setup
cls
echo =======================================================
echo                 Setting up AirDash...                  
echo =======================================================
echo.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ from python.org.
    echo Make sure to tick "Add Python to PATH" during installation.
    pause
    goto menu
)

if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment 'venv'...
    python -m venv venv
) else (
    echo [INFO] Virtual environment 'venv' already exists.
)

echo [INFO] Activating virtual environment and installing dependencies...
call .\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo [SUCCESS] Setup complete! You can now run AirDash.
pause
goto menu

:run
cls
echo =======================================================
echo                   Starting AirDash...                  
echo =======================================================
echo.
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run Setup [1] first.
    pause
    goto menu
)

call .\venv\Scripts\activate
python main.py

echo.
echo [INFO] Application closed.
pause
goto menu

:end
exit
