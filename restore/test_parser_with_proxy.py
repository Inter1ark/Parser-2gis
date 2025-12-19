#!/usr/bin/env python3
"""
Тест парсера с автоматической авторизацией прокси
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Parser2gis import Parser2GIS, ChromeOptions, Configuration
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_parser():
    print("=" * 80)
    print("ТЕСТ ПАРСЕРА С ПРОКСИ")
    print("=" * 80)
    
    # Создаём полную конфигурацию
    config = Configuration()
    
    # Настраиваем Chrome с прокси
    config.chrome.headless = False  # Отключаем headless для прокси с авторизацией
    config.chrome.disable_images = True
    config.chrome.proxy_method = 'sxorg'
    config.chrome.sxorg_api_key = 'okeVhqUalfEdOskA6jJLkPtSWfhLHjZw'  # Правильный ключ
    
    # Настраиваем парсер - лимит 5 организаций для теста
    config.parser.max_records = 5
    
    print("\n✅ Настройки:")
    print(f"   Headless: {config.chrome.headless}")
    print(f"   Прокси метод: {config.chrome.proxy_method}")
    print(f"   API ключ: {config.chrome.sxorg_api_key[:20]}...")
    print(f"   Лимит записей: {config.parser.max_records}")
    
    # Создаём парсер
    print("\n🚀 Создание парсера...")
    parser = Parser2GIS(config)
    
    # Запускаем Chrome
    print("🌐 Запуск Chrome с прокси...")
    parser.start()
    
    # Тестовый URL
    url = "https://2gis.com/moscow/search/кафе"
    print(f"\n🎯 Тестовый URL: {url}")
    print("📊 Запуск парсинга (макс 5 организаций)...")
    
    try:
        results = parser.parse_url(url)
        
        print("\n" + "=" * 80)
        print(f"✅ ПАРСИНГ ЗАВЕРШЕН: получено {len(results)} организаций")
        print("=" * 80)
        
        if results:
            print("\n📋 Примеры найденных организаций:")
            for i, org in enumerate(results[:3], 1):
                print(f"\n{i}. {org.get('name', 'Без названия')}")
                print(f"   Адрес: {org.get('address', 'Нет адреса')}")
                print(f"   Телефон: {org.get('phone', 'Нет телефона')}")
                print(f"   Рейтинг: {org.get('rating', 'Нет рейтинга')}")
        else:
            print("\n⚠️  Результаты пустые - возможно проблема с парсингом")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🛑 Закрытие парсера...")
        try:
            parser.stop()
        except:
            pass

if __name__ == '__main__':
    test_parser()
