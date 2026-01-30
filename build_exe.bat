@echo off
chcp 65001 >nul
echo ============================================
echo Компиляция Parser2GIS в EXE
echo ============================================
echo.

REM Проверка PyInstaller
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo Установка PyInstaller...
    python -m pip install pyinstaller
)

echo Очистка предыдущей сборки...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
if exist "Parser2GIS.spec" del Parser2GIS.spec
echo.

echo Компиляция программы...
pyinstaller --onefile --windowed --icon=logo.ico --name=Parser2GIS --add-data "logo.ico;." --add-data "logo.png;." Parser2gis.py

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo Готово!
    echo EXE файл находится в папке: dist\Parser2GIS.exe
    echo ============================================
    echo.
    start explorer dist
) else (
    echo.
    echo [ОШИБКА] Компиляция не удалась
)

pause
