#!/usr/bin/env python3
"""
Тестовый скрипт для проверки парсера 2GIS
Быстрый тест с минимальными настройками
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Parser2gis import Parser2GIS, Configuration, Writer
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('test')

def test_parser():
    """Test parser with a simple query"""
    
    # Test URL - кафе в Москве (только первая страница)
    test_url = "https://2gis.com/moscow/search/кафе"
    
    logger.info("=" * 60)
    logger.info("ТЕСТ ПАРСЕРА 2GIS")
    logger.info("=" * 60)
    logger.info("URL: %s", test_url)
    logger.info("Лимит: 5 записей (для быстроты)")
    logger.info("=" * 60)
    
    # Create configuration
    config = Configuration()
    config.parser.max_records = 5  # Уменьшаем для быстрого теста
    config.chrome.headless = False  # Показывать браузер для отладки
    config.chrome.disable_images = True
    config.writer.verbose = True
    config.parser.delay_between_clicks = 500  # Задержка между кликами
    
    # Create parser
    parser = Parser2GIS(config)
    
    try:
        # Start browser
        logger.info("Запуск браузера...")
        parser.start()
        
        # Parse URL
        logger.info("Начинаем парсинг...")
        items = parser.parse_url(test_url)
        
        # Show results
        logger.info("=" * 60)
        logger.info("РЕЗУЛЬТАТЫ:")
        logger.info("Найдено элементов: %d", len(items))
        logger.info("=" * 60)
        
        for i, item in enumerate(items, 1):
            logger.info("%d. %s", i, item.name)
            if item.address_name:
                logger.info("   📍 Адрес: %s", item.address_name)
            if item.contact_groups:
                for group in item.contact_groups:
                    for contact in group.contacts:
                        if contact.type == 'phone':
                            logger.info("   📞 Телефон: %s", contact.value)
                        elif contact.type == 'website':
                            logger.info("   🌐 Сайт: %s", contact.url or contact.value)
                        elif contact.type == 'email':
                            logger.info("   📧 Email: %s", contact.value)
            if item.point:
                logger.info("   🗺️  GPS: %.6f, %.6f", item.point.lat, item.point.lon)
            logger.info("")
        
        # Save to file
        if items:
            output_file = "test_results.csv"
            logger.info("=" * 60)
            logger.info("Сохраняем в файл: %s", output_file)
            writer = Writer(config)
            writer.write(items, output_file, 'csv')
            logger.info("✓ Файл сохранён!")
        else:
            logger.warning("⚠ Не найдено ни одной записи для сохранения")
        
    except Exception as e:
        logger.exception("Ошибка: %s", e)
        return False
    finally:
        # Stop browser
        logger.info("Остановка браузера...")
        parser.stop()
    
    logger.info("=" * 60)
    logger.info("ТЕСТ ЗАВЕРШЁН")
    logger.info("=" * 60)
    
    return len(items) > 0

if __name__ == "__main__":
    success = test_parser()
    sys.exit(0 if success else 1)
