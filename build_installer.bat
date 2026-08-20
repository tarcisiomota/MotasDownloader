@echo off
title Media Downloader - Criar Instalador

echo ============================================================
echo  Criando instalador Windows (.exe)
echo ============================================================
echo.

:: Verifica se o build foi feito
if not exist "dist\MediaDownloader\MediaDownloader.exe" (
    echo ERRO: Execute build.bat primeiro para gerar o executavel.
    pause
    exit /b 1
)

:: Cria bitmaps de placeholder para o wizard se nao existirem
if not exist assets\wizard_small.bmp (
    python -c ^
"from PIL import Image, ImageDraw; ^
img = Image.new('RGB', (55,55), (26,26,46)); ^
d = ImageDraw.Draw(img); ^
d.ellipse([4,4,51,51], fill=(196,48,43)); ^
d.polygon([(14,11),(14,44),(44,27)], fill='white'); ^
img.save('assets/wizard_small.bmp')" 2>nul
)
if not exist assets\wizard_banner.bmp (
    python -c ^
"from PIL import Image, ImageDraw; ^
img = Image.new('RGB', (164,314), (26,26,46)); ^
d = ImageDraw.Draw(img); ^
d.ellipse([22,60,142,180], fill=(196,48,43)); ^
d.polygon([(52,80),(52,160),(132,120)], fill='white'); ^
img.save('assets/wizard_banner.bmp')" 2>nul
)

:: Cria pasta de saida
if not exist installer_output mkdir installer_output

:: Localiza o Inno Setup
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"                set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"                      set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"               set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%USERPROFILE%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"  set ISCC="%USERPROFILE%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo.
    echo  Inno Setup nao encontrado!
    echo.
    echo  Baixe e instale em: https://jrsoftware.org/isdl.php
    echo  Em seguida rode este script novamente.
    echo.
    pause
    exit /b 1
)

echo Compilando com Inno Setup...
%ISCC% installer.iss

if errorlevel 1 (
    echo.
    echo ERRO ao criar o instalador.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Instalador gerado em: installer_output\
echo ============================================================
start "" installer_output
pause
