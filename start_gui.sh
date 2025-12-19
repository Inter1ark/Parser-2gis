#!/bin/zsh

# Скрипт для быстрого запуска GUI парсера 2GIS

echo "🚀 Запуск Parser 2GIS GUI..."
echo ""

cd "$(dirname "$0")"

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "Создайте его командой: python3 -m venv venv"
    exit 1
fi

# Активация и запуск
./venv/bin/python Parser2gis.py

echo ""
echo "✅ Парсер завершил работу"
