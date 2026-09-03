@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" "train_v8.py"
echo.
echo Training finished. Model saved to models\watermark_model.pth
pause >nul
