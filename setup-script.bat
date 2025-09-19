@echo off
setlocal enabledelayedexpansion

REM Check if Git is installed, and if not, install it using winget
echo Checking for Git...
git --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Git not found. Installing with winget...
    winget install --id Git.Git -e --source winget
    if !errorlevel! neq 0 (
        echo Failed to install Git with winget. Please install Git manually from https://git-scm.com/downloads and run the script again.
        pause
        exit /b
    )
)
echo Git is installed.

REM Create a directory for the project
mkdir silverScraper

REM Change to the new directory
cd silverScraper

REM Clone the repository
git clone https://github.com/r0831281/silverScraper.git .

REM Check if Python is installed, and if not, install it using winget
echo Checking for Python...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Python not found. Installing with winget...
    winget install --id Python.Python.3 -e --source winget
    echo Please restart your terminal and run this script again.
    pause
    exit /b
)
echo Python is installed.

REM Create a virtual environment
python -m venv .venv

REM Upgrade pip
call .venv\Scripts\python.exe -m pip install --upgrade pip

REM Install dependencies
call .venv\Scripts\python.exe -m pip install -r requirements.txt
call .venv\Scripts\python.exe -m pip install pyinstaller

REM Build the app using PyInstaller
call .venv\Scripts\python.exe -m PyInstaller scraper.spec

echo Setup and build complete!
pause