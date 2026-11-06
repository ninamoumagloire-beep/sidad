@echo off
cd /d "%~dp0"
echo Lancement de SIDAD...
python app.py
if errorlevel 1 py app.py
pause
