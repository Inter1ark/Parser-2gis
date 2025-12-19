#!/usr/bin/env python3
"""
Простая проверка - получаем HTML страницы
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Parser2gis import Parser2GIS, Configuration
import time

config = Configuration()
config.chrome.headless = False

parser = Parser2GIS(config)
parser.start()

print("Открываем 2GIS...")
parser.chrome_remote.navigate("https://2gis.ru/moscow/search/кафе")

print("Ждём 15 секунд...")
time.sleep(15)

print("\n Получаем HTML...")
try:
    html_script = "document.documentElement.outerHTML"
    result = parser.chrome_remote._tab.Runtime.evaluate(expression=html_script)
    html = result.get('result', {}).get('value', '')
    
    # Сохраняем в файл
    with open('/Users/nonnakomissarova/Desktop/Parser2GIS/page_html.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ HTML сохранён (длина: {len(html)} символов)")
    print(f"   Файл: /Users/nonnakomissarova/Desktop/Parser2GIS/page_html.html")
    
    # Ищем что есть на странице
    if '/firm/' in html:
        print("✅ Найдены ссылки на /firm/")
        import re
        firms = re.findall(r'/firm/\d+', html)
        print(f"   Найдено {len(set(firms))} уникальных firm ID")
    else:
        print("⚠️  НЕТ ссылок на /firm/")
        
    if '/branch/' in html:
        print("✅ Найдены ссылки на /branch/")
    else:
        print("⚠️  НЕТ ссылок на /branch/")
        
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
finally:
    time.sleep(5)
    parser.stop()
