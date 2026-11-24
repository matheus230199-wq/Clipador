@echo off
cd /d "%~dp0"
title Clipador GTA VI - NAO FECHE ESTA JANELA
if not exist venv\Scripts\activate.bat goto sem_instalacao
call venv\Scripts\activate.bat

python -c "import psutil, pandas, websockets, streamlit, numpy, requests" >nul 2>&1
if errorlevel 1 goto atualizar
goto abrir

:atualizar
echo.
echo  Atualizando as bibliotecas do programa. Aguarde, pode demorar um pouco...
echo.
pip install -r requirements.txt
if errorlevel 1 goto erro_pip

:abrir
echo.
echo  Abrindo o Clipador no navegador...
echo  Mantenha esta janela aberta. Para encerrar o programa, feche-a.
echo.
start "" /min cmd /c "ping -n 6 127.0.0.1 >nul & start http://localhost:8501"
streamlit run painel.py --server.port 8501
pause
exit /b 0

:erro_pip
echo.
echo ERRO ao instalar as bibliotecas. Verifique a internet e tente de novo.
pause
exit /b 1

:sem_instalacao
echo Primeiro de dois cliques em instalar.bat
pause
exit /b 1
