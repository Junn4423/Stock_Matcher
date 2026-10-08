@echo off
cd /d "%~dp0"
echo Lenh nay se xoa virtual environment .venv de cai lai dependencies.
choice /M "Tiep tuc"
if errorlevel 2 exit /b 0
rmdir /S /Q .venv
 echo Da xoa .venv. Chay lai START_STOCK_MATCHER.bat.
pause
