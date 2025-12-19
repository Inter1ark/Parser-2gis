#!/usr/bin/env python3
"""Простой тест парсера без GUI"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from Parser2gis import Configuration, Parser2GIS, Writer
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)

def main():
    print("\n" + "="*70)
    print("ТЕСТ ПАРСЕРА 2GIS - HEADLESS РЕЖИМ")
    print("="*70 + "\n")
    
    # Загрузка и настройка конфигурации
    config = Configuration.load_config()
    config.chrome.headless = True
    config.chrome.disable_images = True
    config.parser.max_records = 10  # Только 10 для быстрого теста
    config.parser.delay_between_clicks = 500
    
    print(f"✓ Headless: {'ДА' if config.chrome.headless else 'НЕТ'}")
    print(f"✓ Без картинок: {'ДА' if config.chrome.disable_images else 'НЕТ'}")
    print(f"✓ Лимит записей: {config.parser.max_records}")
    print(f"✓ Задержка: {config.parser.delay_between_clicks} мс\n")
    
    # URL и файл
    url = "https://2gis.com/moscow/search/ресторан"
    output = "test_headless_results.csv"
    
    print(f"🔍 URL: {url}")
    print(f"💾 Файл: {output}\n")
    print("="*70 + "\n")
    
    # Создание парсера
    parser = Parser2GIS(config)
    writer = Writer(config)
    
    try:
        # Запуск
        print("🚀 Запуск Chrome в headless режиме...")
        parser.start()
        print("✓ Chrome запущен\n")
        
        # Парсинг
        print("📥 Парсинг страницы...\n")
        items = parser.parse_url(url)
        
        print(f"\n{'='*70}")
        print(f"✅ ПОЛУЧЕНО: {len(items)} организаций")
        print("="*70 + "\n")
        
        if items:
            # Сохранение
            print(f"💾 Сохранение в {output}...")
            writer.write(items, output, 'csv')
            print(f"✅ Сохранено!\n")
            
            # Вывод результатов
            print("📋 РЕЗУЛЬТАТЫ:\n")
            for i, item in enumerate(items, 1):
                phones = []
                emails = []
                website = None
                
                if item.contact_groups:
                    for group in item.contact_groups:
                        for contact in group.contacts:
                            if contact.type == 'phone':
                                phones.append(contact.value)
                            elif contact.type == 'email':
                                emails.append(contact.value)
                            elif contact.type == 'website':
                                website = contact.url or contact.value
                
                print(f"{i}. {item.name}")
                if item.address_name:
                    print(f"   📍 {item.address_name}")
                if phones:
                    print(f"   📞 {', '.join(phones[:2])}")
                if website:
                    print(f"   🌐 {website[:50]}")
                if emails:
                    print(f"   📧 {', '.join(emails[:2])}")
                if item.point:
                    print(f"   🗺️  {item.point.lat:.6f}, {item.point.lon:.6f}")
                print()
            
            print("="*70)
            print(f"✅ ТЕСТ УСПЕШНО ЗАВЕРШЁН")
            print(f"📂 Результаты сохранены в: {output}")
            print("="*70 + "\n")
            
        else:
            print("⚠️  НЕ УДАЛОСЬ ИЗВЛЕЧЬ ДАННЫЕ")
            print("\nВозможные причины:")
            print("1. Сайт изменил структуру")
            print("2. Требуется больше времени ожидания")
            print("3. Нужна отладка селекторов\n")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        return 1
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        print("\n🛑 Остановка Chrome...")
        try:
            parser.stop()
            print("✓ Chrome остановлен\n")
        except:
            pass
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
