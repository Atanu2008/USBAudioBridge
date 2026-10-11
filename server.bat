@echo off
title USB Audio Bridge

echo.
echo ==========================================
echo        USB AUDIO BRIDGE
echo ==========================================
echo.

REM ------------------------------------------
REM ADB location
REM ------------------------------------------

set ADB=C:\Users\Malay Kar\Desktop\platform-tools\adb.exe

REM ------------------------------------------
REM Check ADB
REM ------------------------------------------

if not exist "%ADB%" (
    echo ERROR: adb.exe not found!
    echo.
    echo Expected:
    echo C:\platform-tools\adb.exe
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking phone connection...
echo.

"%ADB%" devices

echo.
echo ------------------------------------------
echo.

REM ------------------------------------------
REM Check whether a phone is connected
REM ------------------------------------------

"%ADB%" get-state >nul 2>&1

if errorlevel 1 (
    echo ERROR: Phone not detected.
    echo.
    echo Make sure:
    echo 1. USB cable is connected
    echo 2. USB Debugging is ON
    echo 3. You accepted "Allow USB debugging"
    echo.
    pause
    exit /b 1
)

echo Phone detected successfully.
echo.

REM ------------------------------------------
REM Create ADB reverse tunnel
REM ------------------------------------------

echo [2/4] Creating USB audio tunnel...
echo.

"%ADB%" reverse tcp:9999 tcp:9999

if errorlevel 1 (
    echo.
    echo ERROR: Could not create ADB reverse tunnel.
    echo.
    pause
    exit /b 1
)

echo ADB reverse tunnel created.
echo.

REM ------------------------------------------
REM Verify tunnel
REM ------------------------------------------

echo [3/4] Verifying tunnel...
echo.

"%ADB%" reverse --list

echo.
echo ------------------------------------------
echo.

REM ------------------------------------------
REM Start Python server
REM ------------------------------------------

echo [4/4] Starting USB Audio Bridge...
echo.

cd /d "C:\Users\Malay Kar\Desktop\USB DEBUG"

python main.py

REM ------------------------------------------
REM If Python server exits
REM ------------------------------------------

echo.
echo ==========================================
echo      USB AUDIO BRIDGE STOPPED
echo ==========================================
echo.

pause