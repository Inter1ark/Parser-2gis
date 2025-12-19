#!/usr/bin/env python3
"""
Быстрый тест для проверки headless режима
"""
import sys
sys.path.insert(0, '/Users/nonnakomissarova/Desktop/Parser2GIS')

from Parser2gis import Configuration, Parser2GIS
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("ТЕСТ HEADLESS РЕЖИМА")
    logger.info("="*60)
    
    # Загружаем конфигурацию
    config = Configuration.load_config()
    
    logger.info(f"📋 Конфиг headless: {config.chrome.headless}")
    logger.info(f"📋 Конфиг proxy_method: {config.chrome.proxy_method}")
    
    # Создаём парсер
    parser = Parser2GIS(config)
    
    logger.info("\n🚀 Запускаем Chrome...")
    parser.start()
    
    logger.info("\n⏸️  Ждём 3 секунды (проверьте - браузер НЕ должен быть виден!)")
    import time
    time.sleep(3)
    
    logger.info("\n🛑 Останавливаем Chrome...")
    parser.stop()
    
    logger.info("\n✅ Тест завершён!")
    logger.info("Если браузер был ВИДЕН - значит headless не работает!")
    logger.info("Если браузер НЕ был виден - headless работает правильно! 👻")
