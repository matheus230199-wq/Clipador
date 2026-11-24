@echo off
setlocal
cd /d "%~dp0"
title Instalador do Clipador GTA VI
echo ==============================================
echo    INSTALADOR DO CLIPADOR GTA VI
echo ==============================================
echo.
set REINICIAR=0

python --version >nul 2>&1
if errorlevel 1 goto instalar_python
echo [1/5] Python encontrado.
goto passo_ffmpeg
:instalar_python
echo [1/5] Instalando o Python...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
set REINICIAR=1

:passo_ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 goto instalar_ffmpeg
echo [2/5] ffmpeg encontrado.
goto passo_deno
:instalar_ffmpeg
echo [2/5] Instalando o ffmpeg...
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
set REINICIAR=1

:passo_deno
where deno >nul 2>&1
if errorlevel 1 goto instalar_deno
echo [3/5] Deno encontrado.
goto verificar
:instalar_deno
echo [3/5] Instalando o Deno...
winget install -e --id DenoLand.Deno --accept-package-agreements --accept-source-agreements
set REINICIAR=1

:verificar
if "%REINICIAR%"=="1" goto reiniciar
goto ambiente

:reiniciar
echo.
echo Alguns programas acabaram de ser instalados.
echo FECHE esta janela e de dois cliques em instalar.bat de novo
echo para o Windows reconhecer os programas novos.
echo.
pause
exit /b 0

:ambiente
echo [4/5] Preparando o ambiente do programa. Pode demorar alguns minutos...
if not exist venv\Scripts\activate.bat python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto erro_pip
echo Instalando componente opcional para o chat da Kick...
pip install curl_cffi
if errorlevel 1 echo Aviso: nao foi possivel instalar o componente opcional. O programa funciona sem ele.

echo [5/5] Criando o atalho na area de trabalho...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Clipador GTA VI.lnk'); $s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo.
echo ==============================================
echo  PRONTO! Use o atalho "Clipador GTA VI" na
echo  area de trabalho para abrir o programa.
echo ==============================================
pause
exit /b 0

:erro_pip
echo.
echo ERRO ao instalar as bibliotecas. Verifique a internet e tente de novo.
pause
exit /b 1
