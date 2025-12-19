#!/usr/bin/env python3
"""
Тест парсера БЕЗ прокси - для проверки работы
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Parser2gis import Parser2GIS, Configuration
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_parser():
    print("=" * 80)
    print("ТЕСТ ПАРСЕРА БЕЗ ПРОКСИ")
    print("=" * 80)
    
    # Создаём конфигурацию БЕЗ прокси
    config = Configuration()
    
    # Настраиваем Chrome
    config.chrome.headless = False  # С GUI чтобы видеть что происходит
    config.chrome.disable_images = True
    config.chrome.proxy_method = None  # БЕЗ ПРОКСИ
    
    # Лимит 5 организаций
    config.parser.max_records = 5
    config.parser.delay_between_clicks = 500  # 0.5 сек между кликами
    
    print("\n✅ Настройки:")
    print(f"   Headless: {config.chrome.headless}")
    print(f"   Прокси: ВЫКЛЮЧЕН")
    print(f"   Лимит записей: {config.parser.max_records}")
    
    # Создаём парсер
    print("\n🚀 Создание парсера...")
    parser = Parser2GIS(config)
    
    # Запускаем Chrome
    print("🌐 Запуск Chrome...")
    parser.start()
    
    # Тестовый URL
    url = "https://2gis.ru/moscow/search/кафе"
    print(f"\n🎯 Тестовый URL: {url}")
    print("📊 Запуск парсинга (макс 5 организаций)...")
    print("⏳ Ждите, это может занять минуту...")
    
    try:
        results = parser.parse_url(url)
        
        print("\n" + "=" * 80)
        print(f"✅ ПАРСИНГ ЗАВЕРШЕН: получено {len(results)} организаций")
        print("=" * 80)
        
        if results:
            print("\n📋 Найденные организации:")
            for i, org in enumerate(results, 1):
                # Извлекаем телефоны из contact_groups
                phones = []
                emails = []
                websites = []
                for group in org.contact_groups:
                    for contact in group.contacts:
                        if contact.type == 'phone':
                            phones.append(contact.value)
                        elif contact.type == 'email':
                            emails.append(contact.value)
                        elif contact.type == 'website':
                            websites.append(contact.url or contact.value)
                
                print(f"\n{i}. {org.name}")
                print(f"   Адрес: {org.address_name or 'Нет адреса'}")
                print(f"   Телефон: {phones[0] if phones else 'Нет телефона'}")
                print(f"   Рейтинг: {org.reviews.general_rating if org.reviews else 'Нет рейтинга'}")
                print(f"   Email: {emails[0] if emails else 'Нет email'}")
                print(f"   Сайт: {websites[0] if websites else 'Нет сайта'}")
        else:
            print("\n⚠️  Результаты пустые - проблема с парсингом")
            
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
