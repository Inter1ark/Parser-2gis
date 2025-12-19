#!/usr/bin/env python3
"""Тест нового парсера с правильным методом (клики по ссылкам)"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from Parser2gis import Configuration, Parser2GIS, Writer
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)

def main():
    print("\n" + "="*70)
    print("ТЕСТ НОВОГО ПАРСЕРА 2GIS (метод с кликами)")
    print("="*70 + "\n")
    
    # Конфигурация
    config = Configuration.load_config()
    config.chrome.headless = False  # БЕЗ headless чтобы видеть процесс
    config.chrome.disable_images = True
    config.parser.max_records = 5  # Только 5 для быстрого теста
    config.parser.delay_between_clicks = 300  # 300мс задержка
    
    print(f"✓ Headless: {'ДА' if config.chrome.headless else 'НЕТ (для отладки)'}")
    print(f"✓ Без картинок: ДА")
    print(f"✓ Лимит: {config.parser.max_records} записей")
    print(f"✓ Задержка: {config.parser.delay_between_clicks} мс\n")
    
    url = "https://2gis.com/moscow/search/кафе"
    output = "test_new_parser.csv"
    
    print(f"🔍 URL: {url}")
    print(f"💾 Файл: {output}\n")
    print("="*70 + "\n")
    
    parser = Parser2GIS(config)
    writer = Writer(config)
    
    try:
        print("🚀 Запуск браузера...")
        parser.start()
        print("✓ Браузер запущен\n")
        
        print("📥 Начинаем парсинг...\n")
        items = parser.parse_url(url)
        
        print(f"\n{'='*70}")
        print(f"✅ РЕЗУЛЬТАТ: {len(items)} организаций")
        print("="*70 + "\n")
        
        if items:
            print(f"💾 Сохранение...")
            writer.write(items, output, 'csv')
            print(f"✓ Сохранено в {output}\n")
            
            print("📋 ДАННЫЕ:\n")
            for i, item in enumerate(items, 1):
                phones = []
                if item.contact_groups:
                    for group in item.contact_groups:
                        for contact in group.contacts:
                            if contact.type == 'phone':
                                phones.append(contact.value)
                
                print(f"{i}. {item.name}")
                print(f"   ID: {item.id}")
                if item.address_name:
                    print(f"   📍 {item.address_name}")
                if phones:
                    print(f"   📞 {', '.join(phones)}")
                if item.point:
                    print(f"   🗺️  {item.point.lat:.6f}, {item.point.lon:.6f}")
                print()
            
            print("="*70)
            print(f"✅ УСПЕХ! Данные извлечены правильно")
            print("="*70 + "\n")
        else:
            print("⚠️  Данные не получены\n")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано")
        return 1
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        print("🛑 Остановка браузера...")
        parser.stop()
        print("✓ Завершено\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
