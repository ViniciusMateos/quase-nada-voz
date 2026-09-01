@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python app.py
echo.
echo O app parou. Pressione qualquer tecla para fechar.
pause >nul
