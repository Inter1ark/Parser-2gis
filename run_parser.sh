#!/bin/bash

# Скрипт для быстрого запуска Parser 2GIS

cd "$(dirname "$0")"

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "Создаём виртуальное окружение..."
    python3 -m venv venv
    echo "✓ Виртуальное окружение создано"
    
    echo "Устанавливаем зависимости..."
    source venv/bin/activate
    pip install requests pydantic pychrome psutil openpyxl
    echo "✓ Зависимости установлены"
else
    source venv/bin/activate
fi

# Запуск программы
echo "🚀 Запуск Parser 2GIS..."
python3 Parser2gis.py "$@"
