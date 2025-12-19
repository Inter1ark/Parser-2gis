#!/usr/bin/env python3
"""Отладка парсера - показывает что реально на странице"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from Parser2gis import Configuration, ChromeRemote, ChromeOptions
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger('debug')

def main():
    print("\n" + "="*70)
    print("ОТЛАДКА ПАРСЕРА - АНАЛИЗ СТРУКТУРЫ СТРАНИЦЫ")
    print("="*70 + "\n")
    
    # Конфигурация
    chrome_options = ChromeOptions()
    chrome_options.headless = False  # БЕЗ headless для отладки!
    chrome_options.disable_images = True
    
    url = "https://2gis.com/moscow/search/ресторан"
    
    print(f"🔍 URL: {url}")
    print(f"⚠️  Headless: ВЫКЛ (для отладки)\n")
    print("="*70 + "\n")
    
    chrome = ChromeRemote(chrome_options, response_patterns=[])
    
    try:
        print("🚀 Запуск Chrome...")
        chrome.start()
        print("✓ Chrome запущен\n")
        
        print("📄 Открываем страницу...")
        chrome.navigate(url)
        print("✓ Страница открыта\n")
        
        print("⏱️  Ждём 10 секунд для загрузки...")
        time.sleep(10)
        
        # Анализ структуры
        print("\n" + "="*70)
        print("АНАЛИЗ СТРУКТУРЫ СТРАНИЦЫ")
        print("="*70 + "\n")
        
        debug_script = """
        (function() {
            var report = {
                title: document.title,
                url: window.location.href,
                selectors: {}
            };
            
            // Пробуем разные селекторы
            var selectorsToTry = [
                'div[class*="miniCard"]',
                'article[class*="card"]',
                'div[class*="searchCard"]',
                'a[class*="_itemLink"]',
                '[data-test="miniCard"]',
                '[class*="organic"]',
                '[class*="searchResults"]',
                '[class*="resultList"]',
                'a[href*="/firm/"]',
                'div[class*="Card"]',
                'div[class*="card"]',
                'div[class*="item"]',
                'div[class*="Item"]'
            ];
            
            selectorsToTry.forEach(function(selector) {
                var elements = document.querySelectorAll(selector);
                report.selectors[selector] = elements.length;
            });
            
            // Найти все классы на странице
            var allClasses = new Set();
            var allElements = document.querySelectorAll('*');
            for (var i = 0; i < Math.min(allElements.length, 1000); i++) {
                var classes = allElements[i].className;
                if (typeof classes === 'string' && classes) {
                    classes.split(' ').forEach(function(cls) {
                        if (cls && (cls.includes('card') || cls.includes('Card') || 
                                   cls.includes('item') || cls.includes('Item') ||
                                   cls.includes('search') || cls.includes('Search') ||
                                   cls.includes('result') || cls.includes('Result'))) {
                            allClasses.add(cls);
                        }
                    });
                }
            }
            report.relevantClasses = Array.from(allClasses).slice(0, 20);
            
            // Ищем ссылки на фирмы
            var firmLinks = document.querySelectorAll('a[href*="/firm/"]');
            report.firmLinksCount = firmLinks.length;
            
            // Пример первой ссылки
            if (firmLinks.length > 0) {
                var firstLink = firmLinks[0];
                report.firstFirmExample = {
                    href: firstLink.href,
                    text: firstLink.textContent.trim().substring(0, 100),
                    classes: firstLink.className,
                    parentClasses: firstLink.parentElement ? firstLink.parentElement.className : 'нет'
                };
            }
            
            return report;
        })();
        """
        
        result = chrome._tab.Runtime.evaluate(expression=debug_script)
        
        if result and 'result' in result and 'value' in result['result']:
            report = result['result']['value']
            
            print(f"📄 Title: {report.get('title', 'N/A')}")
            print(f"🔗 URL: {report.get('url', 'N/A')}\n")
            
            print("🔍 РЕЗУЛЬТАТЫ ПОИСКА ПО СЕЛЕКТОРАМ:\n")
            selectors = report.get('selectors', {})
            for selector, count in sorted(selectors.items(), key=lambda x: -x[1]):
                if count > 0:
                    print(f"  ✓ {selector}: {count} элементов")
                else:
                    print(f"  ✗ {selector}: 0 элементов")
            
            print(f"\n📊 Ссылок на фирмы (/firm/): {report.get('firmLinksCount', 0)}")
            
            if report.get('firstFirmExample'):
                ex = report['firstFirmExample']
                print("\n📌 ПРИМЕР ПЕРВОЙ ССЫЛКИ:")
                print(f"  URL: {ex.get('href', 'N/A')}")
                print(f"  Текст: {ex.get('text', 'N/A')[:80]}...")
                print(f"  Классы ссылки: {ex.get('classes', 'нет')}")
                print(f"  Классы родителя: {ex.get('parentClasses', 'нет')}")
            
            if report.get('relevantClasses'):
                print("\n🏷️  РЕЛЕВАНТНЫЕ КЛАССЫ (первые 20):")
                for cls in report['relevantClasses']:
                    print(f"  - {cls}")
        
        print("\n" + "="*70)
        print("❗ БРАУЗЕР ОСТАЕТСЯ ОТКРЫТЫМ ДЛЯ ИНСПЕКЦИИ")
        print("❗ Нажмите Ctrl+C чтобы закрыть")
        print("="*70 + "\n")
        
        # Держим браузер открытым
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n⚠️  Закрытие...")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        print("🛑 Остановка Chrome...")
        chrome.stop()
        print("✓ Готово\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
