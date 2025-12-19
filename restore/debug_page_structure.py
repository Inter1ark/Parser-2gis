#!/usr/bin/env python3
"""
Дебаг - смотрим что на самом деле на странице 2GIS
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Parser2gis import Parser2GIS, Configuration
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def debug_page():
    print("=" * 80)
    print("ДЕБАГ СТРУКТУРЫ СТРАНИЦЫ 2GIS")
    print("=" * 80)
    
    config = Configuration()
    config.chrome.headless = False
    config.chrome.disable_images = True
    
    parser = Parser2GIS(config)
    parser.start()
    
    url = "https://2gis.ru/moscow/search/кафе"
    print(f"\n📍 Открываем: {url}")
    
    parser.chrome_remote.navigate(url)
    print("⏳ Ждём загрузки... (10 сек)")
    import time
    time.sleep(10)
    
    # Проверяем структуру страницы
    debug_script = """
    (function() {
        var info = {
            url: window.location.href,
            totalLinks: document.querySelectorAll('a').length,
            firmLinks: document.querySelectorAll('a[href*="firm"]').length,
            branchLinks: document.querySelectorAll('a[href*="branch"]').length,
            dataTestCards: document.querySelectorAll('[data-test*="card"]').length,
            classCards: document.querySelectorAll('[class*="card"]').length,
            miniCards: document.querySelectorAll('[class*="minicard"]').length,
            sampleLinks: []
        };
        
        var allLinks = document.querySelectorAll('a');
        for (var i = 0; i < Math.min(20, allLinks.length); i++) {
            var link = allLinks[i];
            var href = link.getAttribute('href') || '';
            var text = link.textContent.trim().substring(0, 50);
            var classes = link.className;
            
            if (href || text) {
                info.sampleLinks.push({
                    href: href,
                    text: text,
                    classes: classes
                });
            }
        }
        
        return info;
    })();
    """
    
    try:
        result = parser.chrome_remote._tab.Runtime.evaluate(expression=debug_script)
        info = result.get('result', {}).get('value', {})
        
        print("\n📊 ИНФОРМАЦИЯ О СТРАНИЦЕ:")
        print(f"   URL: {info.get('url')}")
        print(f"   Всего ссылок: {info.get('totalLinks')}")
        print(f"   Ссылок с 'firm': {info.get('firmLinks')}")
        print(f"   Ссылок с 'branch': {info.get('branchLinks')}")
        print(f"   Элементов [data-test*='card']: {info.get('dataTestCards')}")
        print(f"   Элементов [class*='card']: {info.get('classCards')}")
        print(f"   Элементов [class*='minicard']: {info.get('miniCards')}")
        
        print("\n🔗 ПЕРВЫЕ 20 ССЫЛОК НА СТРАНИЦЕ:")
        for i, link in enumerate(info.get('sampleLinks', []), 1):
            print(f"\n{i}.")
            print(f"   Текст: {link.get('text')}")
            print(f"   Href: {link.get('href')[:100] if link.get('href') else 'нет'}")
            print(f"   Classes: {link.get('classes')[:80] if link.get('classes') else 'нет'}")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n\n⏸️  Оставляю браузер открытым на 30 секунд для проверки...")
        print("   Посмотрите что отображается в браузере!")
        time.sleep(30)
        
        parser.stop()

if __name__ == '__main__':
    debug_page()
