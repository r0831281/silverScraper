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

REM Check if Node.js is installed, and if not, install it using winget
echo Checking for Node.js...
node --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Node.js not found. Installing with winget...
    winget install --id OpenJS.NodeJS -e --source winget
    if !errorlevel! neq 0 (
        echo Failed to install Node.js with winget. Please install Node.js manually from https://nodejs.org/ and run the script again.
        pause
        exit /b
    )
    echo Node.js has been installed. Please restart your terminal and run this script again.
    pause
    exit /b
)
echo Node.js is installed.

REM Install npm dependencies in the proxy folder
echo Installing npm dependencies...
echo Current directory before cd: %CD%
cd proxy
echo Current directory after cd proxy: %CD%
call npm install
if !errorlevel! neq 0 (
    echo Failed to install npm dependencies. Please check your Node.js installation and try again.
    cd ..
    pause
    exit /b
)
echo npm dependencies installed.
cd ..
echo Current directory after cd ..: %CD%
echo Continuing with Python setup...

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

call .venv\Scripts\activate.bat

REM Upgrade pip
call pip install --upgrade pip

REM Install all dependencies except PyInstaller
call pip install -r requirements.txt

REM Explicitly install PyInstaller
call pip install pyinstaller

REM Build the app using PyInstaller
echo Building the app with PyInstaller...
call pyinstaller scraper.spec

echo Setup and build complete!
pause