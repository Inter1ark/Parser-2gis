#!/usr/bin/env python3
"""
Тест: сохранение HTML при использовании прокси
"""
import sys
import time
sys.path.insert(0, '/Users/nonnakomissarova/Desktop/Parser2GIS')
from Parser2gis import Parser2GISParser, Configuration

def test_proxy_html():
    print("="*80)
    print("ТЕСТ ПРОКСИ: СОХРАНЕНИЕ HTML")
    print("="*80)
    
    # Конфигурация
    config = Configuration()
    config.parser.headless = False
    config.parser.max_records = 1
    config.proxy.method = 'sxorg'
    config.proxy.sxorg_api_key = 'okeVhqUalfEdOskA6jJLkPtSWfhLHjZw'
    
    print(f"\n✅ Настройки:")
    print(f"   Прокси: {config.proxy.method}")
    print(f"   Headless: {config.parser.headless}")
    
    try:
        # Создаем парсер
        print("\n🚀 Создание парсера...")
        parser = Parser2GISParser(config)
        
        # Запускаем Chrome
        print("🌐 Запуск Chrome с прокси...")
        parser.start()
        
        # Переходим на страницу
        url = "https://2gis.ru/moscow/search/кафе"
        print(f"\n🎯 URL: {url}")
        print("⏳ Загрузка страницы...")
        
        parser.chrome_remote.navigate(url)
        time.sleep(10)  # Даем больше времени на загрузку
        
        # Получаем HTML
        print("\n📄 Получение HTML...")
        html_result = parser.chrome_remote._tab.Runtime.evaluate(expression='document.documentElement.outerHTML')
        html_content = html_result.get('result', {}).get('value', '')
        
        # Сохраняем в файл
        output_file = '/Users/nonnakomissarova/Desktop/Parser2GIS/proxy_page.html'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML сохранен: {output_file}")
        print(f"   Размер: {len(html_content)} символов")
        
        # Ищем firm ID
        import re
        firm_ids = re.findall(r'/firm/(\d+)', html_content)
        print(f"\n🔍 Найдено firm ID: {len(set(firm_ids))}")
        if firm_ids:
            print(f"   Примеры: {', '.join(list(set(firm_ids))[:5])}")
        
        # Проверяем на блокировку
        if 'captcha' in html_content.lower():
            print("\n⚠️  ОБНАРУЖЕНА КАПЧА!")
        if 'access denied' in html_content.lower():
            print("\n⚠️  ДОСТУП ЗАБЛОКИРОВАН!")
        if len(html_content) < 1000:
            print("\n⚠️  HTML слишком короткий - возможно ошибка загрузки")
            print(f"   Содержимое: {html_content[:500]}")
        
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

if __name__ == "__main__":
    test_proxy_html()
