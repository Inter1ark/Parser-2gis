#!/usr/bin/env python3
"""Проверка что реально на странице 2GIS"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from Parser2gis import Configuration, ChromeRemote, ChromeOptions
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')

def main():
    print("\n" + "="*70)
    print("ПРОВЕРКА СТРУКТУРЫ СТРАНИЦЫ 2GIS")
    print("="*70 + "\n")
    
    chrome_options = ChromeOptions()
    chrome_options.headless = False  # БЕЗ headless
    chrome_options.disable_images = True
    
    url = "https://2gis.com/moscow/search/кафе"
    
    print(f"🔍 URL: {url}\n")
    
    chrome = ChromeRemote(chrome_options, response_patterns=[])
    
    try:
        print("🚀 Запуск Chrome...")
        chrome.start()
        print("✓ Готово\n")
        
        print("📄 Открываем страницу...")
        chrome.navigate(url)
        print("✓ Готово\n")
        
        print("⏱️  Ждём 15 секунд...")
        time.sleep(15)
        
        print("\n" + "="*70)
        print("АНАЛИЗ СТРАНИЦЫ")
        print("="*70 + "\n")
        
        # Проверяем разные типы ссылок
        check_script = """
        (function() {
            var report = {};
            
            // Все ссылки
            var allLinks = document.querySelectorAll('a');
            report.totalLinks = allLinks.length;
            
            // Ссылки с /firm/
            var firmLinks = document.querySelectorAll('a[href*="/firm/"]');
            report.firmLinks = firmLinks.length;
            
            // Ссылки с ?stat=
            var statLinks = document.querySelectorAll('a[href*="?stat="]');
            report.statLinks = statLinks.length;
            
            // Примеры ссылок
            report.examples = [];
            for (var i = 0; i < Math.min(firmLinks.length, 5); i++) {
                report.examples.push({
                    href: firmLinks[i].href,
                    text: firmLinks[i].textContent.trim().substring(0, 80),
                    hasStatParam: firmLinks[i].href.includes('?stat=')
                });
            }
            
            // Проверяем селекторы из оригинального парсера
            var validLinks = 0;
            for (var i = 0; i < allLinks.length; i++) {
                var href = allLinks[i].getAttribute('href');
                if (href && href.match(/\/(firm|station)\/.*\\?stat=/)) {
                    validLinks++;
                }
            }
            report.validLinksCount = validLinks;
            
            return report;
        })();
        """
        
        result = chrome._tab.Runtime.evaluate(expression=check_script)
        
        if result and 'result' in result and 'value' in result['result']:
            report = result['result']['value']
            
            print(f"📊 СТАТИСТИКА:")
            print(f"  - Всего ссылок: {report.get('totalLinks', 0)}")
            print(f"  - Ссылок с /firm/: {report.get('firmLinks', 0)}")
            print(f"  - Ссылок с ?stat=: {report.get('statLinks', 0)}")
            print(f"  - Валидных ссылок (firm/station + ?stat=): {report.get('validLinksCount', 0)}")
            
            examples = report.get('examples', [])
            if examples:
                print(f"\n📌 ПРИМЕРЫ ССЫЛОК (первые 5):\n")
                for i, ex in enumerate(examples, 1):
                    print(f"{i}. {ex.get('text', 'N/A')}")
                    print(f"   URL: {ex.get('href', 'N/A')[:100]}")
                    print(f"   Есть ?stat=: {ex.get('hasStatParam', False)}")
                    print()
            else:
                print("\n⚠️  Примеры ссылок не найдены!")
        
        print("="*70)
        print("❗ Браузер остается открытым для инспекции")
        print("❗ Откройте DevTools (F12) и проверьте элементы")
        print("❗ Нажмите Ctrl+C чтобы закрыть")
        print("="*70 + "\n")
        
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
        print("🛑 Остановка...")
        chrome.stop()
        print("✓ Готово\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
