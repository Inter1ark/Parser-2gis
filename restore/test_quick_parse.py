#!/usr/bin/env python3
"""
Быстрый тест парсинга с подробными логами
"""
import sys
sys.path.insert(0, '/Users/nonnakomissarova/Desktop/Parser2GIS')

from Parser2gis import Configuration, Parser2GIS
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)

if __name__ == "__main__":
    print("="*60)
    print("ТЕСТ ПАРСИНГА С HEADLESS")
    print("="*60)
    
    # Загружаем конфигурацию
    config = Configuration.load_config()
    config.parser.max_records = 5  # Лимит для теста
    
    print(f"\n📋 Настройки:")
    print(f"   - headless: {config.chrome.headless}")
    print(f"   - disable_images: {config.chrome.disable_images}")
    print(f"   - max_records: {config.parser.max_records}")
    
    # Создаём парсер
    parser = Parser2GIS(config)
    
    try:
        print(f"\n🚀 Запускаем Chrome...")
        parser.start()
        
        print(f"\n📡 Начинаем парсинг...")
        url = "https://2gis.ru/moscow/search/кафе"
        items = parser.parse_url(url)
        
        print(f"\n✅ Результаты:")
        print(f"   Найдено: {len(items)} организаций")
        
        if items:
            print(f"\n📋 Первые 3 организации:")
            for i, item in enumerate(items[:3], 1):
                print(f"\n   {i}. {item.name}")
                print(f"      Адрес: {item.address_name}")
                if item.contact_groups:
                    phones = []
                    for group in item.contact_groups:
                        for contact in group.contacts:
                            if contact.type == 'phone':
                                phones.append(contact.value)
                    if phones:
                        print(f"      Телефоны: {', '.join(phones)}")
        
        print(f"\n🛑 Останавливаем Chrome...")
        parser.stop()
        
        print(f"\n✅ Тест завершён успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        parser.stop()
