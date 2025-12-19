import sys
import time
from Parser2gis import *

# Настройки
config = Configuration()
config.chrome.headless = False
config.chrome.disable_images = True

# Создаём парсер
parser = Parser2GIS(config)
parser.start()

# Тестовая организация
test_firm_id = '70000001007179642'
url = f'https://2gis.com/firm/{test_firm_id}'

print(f'\n🔍 Открываем: {url}')
print('=' * 60)

# Навигация
parser.chrome_remote._tab.Page.navigate(url=url)
time.sleep(8)  # Ждём загрузки

print('\n📸 Проверяем содержимое страницы...\n')

# 1. Проверяем title
result = parser.chrome_remote._tab.Runtime.evaluate(expression='document.title')
print(f'✓ Title: {result["result"]["value"]}\n')

# 2. Проверяем длину body
result = parser.chrome_remote._tab.Runtime.evaluate(expression='document.body.innerText.length')
print(f'✓ Body length: {result["result"]["value"]} символов\n')

# 3. Ищем телефоны простым способом
js_code = r'''
(function() {
    var result = {
        telLinks: [],
        allLinks: 0,
        bodySnippet: ''
    };
    
    // Все ссылки
    result.allLinks = document.querySelectorAll('a').length;
    
    // tel: ссылки
    var telLinks = document.querySelectorAll('a[href^="tel:"]');
    telLinks.forEach(function(link) {
        result.telLinks.push({
            href: link.href,
            text: link.innerText
        });
    });
    
    // Кусок текста
    result.bodySnippet = document.body.innerText.substring(0, 300);
    
    return result;
})()
'''

result = parser.chrome_remote._tab.Runtime.evaluate(expression=js_code)
data = result['result']['value']

print(f'✓ Всего ссылок на странице: {data["allLinks"]}')
print(f'✓ tel: ссылок: {len(data["telLinks"])}')
if data['telLinks']:
    print('\n📞 Найденные телефоны:')
    for link in data['telLinks']:
        print(f'   • {link["text"]} ({link["href"]})')
else:
    print('   ⚠️ tel: ссылки не найдены')

print(f'\n📄 Начало текста страницы:')
print(f'   {data["bodySnippet"][:200]}...')

print('\n' + '=' * 60)
print('✅ Отладка завершена')

parser.stop()
