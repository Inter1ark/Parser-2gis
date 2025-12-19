#!/bin/bash
# Быстрый тест парсера

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "Запустите сначала: ./run_parser.sh"
    exit 1
fi

source venv/bin/activate

echo "🧪 Запуск тестового парсинга..."
echo ""
python3 test_parser.py

echo ""
echo "📁 Результаты сохранены в: test_results.csv"
