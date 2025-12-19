#!/usr/bin/env python3
"""Быстрый тест парсера - проверка работоспособности"""

import sys
from Parser2gis import Configuration, Parser2GIS, Writer
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('parser-2gis')

def main():
    print("=" * 60)
    print("БЫСТРЫЙ ТЕСТ ПАРСЕРА 2GIS")
    print("=" * 60)
    
    # Загрузка конфигурации
    config = Configuration.load_config()
    
    # Включаем headless режим
    config.chrome.headless = True
    config.chrome.disable_images = True
    
    # Ограничиваем количество записей для быстрого теста
    config.parser.max_records = 15
    
    print(f"\n✓ Headless режим: {'ВКЛ' if config.chrome.headless else 'ВЫКЛ'}")
    print(f"✓ Отключить изображения: {'ДА' if config.chrome.disable_images else 'НЕТ'}")
    print(f"✓ Максимум записей: {config.parser.max_records}")
    
    # URL для тестирования
    test_url = "https://2gis.com/moscow/search/кафе"
    output_file = "quick_test_results.csv"
    
    print(f"\n🔍 URL: {test_url}")
    print(f"💾 Выходной файл: {output_file}")
    print("\n" + "=" * 60)
    
    # Создаем парсер
    parser = Parser2GIS(config)
    
    try:
        # Запускаем браузер
        print("\n🚀 Запуск браузера...")
        parser.start()
        
        # Парсим URL
        print(f"\n📥 Начинаем парсинг...")
        items = parser.parse_url(test_url)
        
        print(f"\n✅ Получено {len(items)} организаций")
        
        # Сохраняем результаты
        if items:
            print(f"\n💾 Сохранение в {output_file}...")
            writer = Writer(config)
            writer.write(items, output_file, 'csv')
            print(f"✅ Успешно сохранено в {output_file}")
            
            # Показываем несколько примеров
            print(f"\n📋 Первые {min(5, len(items))} организаций:")
            for i, item in enumerate(items[:5], 1):
                phones = []
                if item.contact_groups:
                    for group in item.contact_groups:
                        for contact in group.contacts:
                            if contact.type == 'phone':
                                phones.append(contact.value)
                phone_str = phones[0] if phones else "нет"
                print(f"  {i}. {item.name}")
                print(f"     📍 {item.address_name or 'адрес не указан'}")
                print(f"     📞 {phone_str}")
        else:
            print("\n⚠️  Данные не найдены!")
            print("Возможные причины:")
            print("  1. Сайт изменил структуру страницы")
            print("  2. Требуется больше времени на загрузку")
            print("  3. Нужно проверить селекторы")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Останавливаем браузер
        print("\n🛑 Остановка браузера...")
        parser.stop()
    
    print("\n" + "=" * 60)
    print("ТЕСТ ЗАВЕРШЁН")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
