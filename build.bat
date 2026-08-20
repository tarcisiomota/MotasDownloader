@echo off
setlocal enabledelayedexpansion
title Mota's Downloader - Build

echo ============================================================
echo  Mota's Downloader - Build Script
echo ============================================================
echo.

:: ── 1. Dependencias Python ───────────────────────────────────
echo [1/4] Instalando dependencias Python...
pip install -r requirements.txt --quiet
if errorlevel 1 ( echo ERRO ao instalar dependencias. & pause & exit /b 1 )

:: ── 2. FFmpeg ────────────────────────────────────────────────
echo [2/4] Verificando ffmpeg...
if not exist "bin\ffmpeg.exe" (
    echo     Baixando ffmpeg estatico...
    if not exist bin mkdir bin
    :: Usa PowerShell para baixar e extrair o ffmpeg
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip';" ^
      "$zip = 'bin\ffmpeg.zip';" ^
      "Write-Host '    Baixando...';" ^
      "Invoke-WebRequest $url -OutFile $zip -UseBasicParsing;" ^
      "Write-Host '    Extraindo...';" ^
      "Expand-Archive $zip -DestinationPath 'bin\ffmpeg_tmp' -Force;" ^
      "$exe = Get-ChildItem 'bin\ffmpeg_tmp' -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1;" ^
      "Copy-Item $exe.FullName 'bin\ffmpeg.exe';" ^
      "$ffprobe = Get-ChildItem 'bin\ffmpeg_tmp' -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1;" ^
      "if ($ffprobe) { Copy-Item $ffprobe.FullName 'bin\ffprobe.exe' };" ^
      "Remove-Item $zip -Force;" ^
      "Remove-Item 'bin\ffmpeg_tmp' -Recurse -Force;" ^
      "Write-Host '    ffmpeg pronto.'"
    if errorlevel 1 ( echo ERRO ao baixar ffmpeg. & pause & exit /b 1 )
) else (
    echo     ffmpeg ja presente, pulando.
)

:: ── 3. Icone ─────────────────────────────────────────────────
echo [3/4] Gerando icone...
if not exist assets mkdir assets
python -c ^
"from PIL import Image, ImageDraw; ^
img = Image.new('RGBA', (256,256), (26,26,46,255)); ^
d = ImageDraw.Draw(img); ^
d.ellipse([20,20,236,236], fill=(196,48,43,255)); ^
d.polygon([(90,60),(90,196),(200,128)], fill='white'); ^
img.save('assets/icon.ico')" 2>nul
if errorlevel 1 ( echo     Aviso: icone nao gerado, continuando sem ele. )

:: ── 4. PyInstaller ───────────────────────────────────────────
echo [4/4] Compilando com PyInstaller...
if exist dist\MediaDownloader rmdir /s /q dist\MediaDownloader

set ICON_OPT=
if exist assets\icon.ico set ICON_OPT=--icon=assets\icon.ico

set FFMPEG_DATA=
if exist bin\ffmpeg.exe set FFMPEG_DATA=--add-data "bin\ffmpeg.exe;bin"
if exist bin\ffprobe.exe set FFMPEG_DATA=%FFMPEG_DATA% --add-data "bin\ffprobe.exe;bin"

pyinstaller ^
    --noconfirm ^
    --windowed ^
    --name MediaDownloader ^
    %ICON_OPT% ^
    %FFMPEG_DATA% ^
    --hidden-import=customtkinter ^
    --hidden-import=yt_dlp ^
    --hidden-import=spotdl ^
    --collect-all customtkinter ^
    --collect-all yt_dlp ^
    app.py

if errorlevel 1 ( echo ERRO no PyInstaller. & pause & exit /b 1 )

echo.
echo ============================================================
echo  Build concluido!
echo  Executavel em: dist\MediaDownloader\MediaDownloader.exe
echo.
echo  Para criar o instalador .exe rode: build_installer.bat
echo ============================================================
pause
