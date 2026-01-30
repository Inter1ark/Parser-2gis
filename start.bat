@echo off
chcp 65001 >nul
echo ============================================
echo Parser 2GIS - Запуск программы
echo ============================================
echo.

REM Проверка Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python с https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python найден
python --version
echo.

REM Проверка и установка зависимостей
echo Проверка зависимостей...
python -c "import pychrome, requests, pydantic, psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo Установка необходимых библиотек...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости
        pause
        exit /b 1
    )
    echo [OK] Зависимости установлены
) else (
    echo [OK] Все зависимости установлены
)
echo.

echo Запуск Parser2gis...
echo.
python Parser2gis.py

if %errorlevel% neq 0 (
    echo.
    echo [ОШИБКА] Программа завершилась с ошибкой
    pause
)
