#!/usr/bin/env python3
"""
Быстрый тест после исправлений
"""
import sys
sys.path.insert(0, '/Users/nonnakomissarova/Desktop/Parser2GIS')
from Parser2gis import Parser2GISParser, Configuration

def quick_test():
    print("="*80)
    print("БЫСТРЫЙ ТЕСТ ПОСЛЕ ИСПРАВЛЕНИЙ")
    print("="*80)
    
    config = Configuration()
    config.chrome.headless = True
    config.chrome.proxy_method = 'sxorg'
    config.chrome.sxorg_api_key = 'okeVhqUalfEdOskA6jJLkPtSWfhLHjZw'
    config.parser.max_records = 3
    
    print(f"\n✅ Настройки:")
    print(f"   Headless: {config.chrome.headless}")
    print(f"   Прокси: {config.chrome.proxy_method}")
    print(f"   Лимит: {config.parser.max_records}")
    
    try:
        print("\n🚀 Запуск парсера...")
        parser = Parser2GISParser(config)
        parser.start()
        
        # ВАЖНО: Используем 2gis.RU вместо 2gis.com
        url = "https://2gis.ru/moscow/search/кафе"
        print(f"\n🎯 URL: {url}")
        print("⏳ Парсинг...")
        
        results = parser.parse_url(url)
        
        print(f"\n{'='*80}")
        print(f"✅ РЕЗУЛЬТАТ: {len(results)} организаций")
        print(f"{'='*80}")
        
        if results:
            for i, org in enumerate(results[:3], 1):
                # Извлекаем контакты
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
                print(f"   Адрес: {org.address_name or 'Нет'}")
                print(f"   Телефон: {phones[0] if phones else 'Нет'}")
                print(f"   Email: {emails[0] if emails else 'Нет'}")
                print(f"   Сайт: {websites[0][:50] + '...' if websites else 'Нет'}")
        else:
            print("\n⚠️  Результаты пустые")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🛑 Закрытие...")
        try:
            parser.stop()
        except:
            pass

if __name__ == "__main__":
    quick_test()
