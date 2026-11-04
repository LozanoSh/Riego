@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
.venv\Scripts\python.exe app.py
if errorlevel 1 goto error
exit /b 0
:error
echo No se pudo iniciar. Verifica Python 3.12 o superior y la conexion para instalar dependencias.
pause
exit /b 1
