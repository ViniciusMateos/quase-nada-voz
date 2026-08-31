@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python quase_nada_voz.py
echo.
echo O script parou. Pressione qualquer tecla para fechar.
pause >nul
