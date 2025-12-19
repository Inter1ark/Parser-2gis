# 🚀 БЫСТРЫЙ СТАРТ - Parser 2GIS

## ✅ Что исправлено

### 1. **РЕАЛЬНЫЙ ПАРСИНГ** вместо имитации
   - ✓ Извлечение данных из API ответов 2GIS
   - ✓ Парсинг HTML контента с множественными селекторами
   - ✓ Автоматическая прокрутка и подзагрузка данных
   - ✓ Обработка до 3 попыток извлечения данных

### 2. **СОЗДАНИЕ ПРОКСИ SX.ORG**
   - ✓ Добавлена кнопка "Создать новый прокси SX.ORG" в GUI
   - ✓ Функция `create_sxorg_proxy()` работает
   - ✓ Выбор типа прокси (Residential/Mobile/Corporate)
   - ✓ Выбор протокола (HTTP/HTTPS/SOCKS5)

### 3. **Исправлены ошибки Pydantic V2**
   - ✓ `.dict()` → `.model_dump()`
   - ✓ `.__fields__` → `.model_fields`

## 📋 Что парсится

- ✅ ID организации
- ✅ Название
- ✅ Адрес
- ✅ Телефоны
- ✅ Сайты
- ✅ Email
- ✅ GPS координаты
- ✅ Рубрики
- ✅ URL на 2GIS

## 🎯 Как использовать

### Вариант 1: Тестовый запуск (рекомендуется для проверки)

```bash
cd /Users/nonnakomissarova/Downloads
source venv/bin/activate
python3 test_parser.py
```

Это запустит быстрый тест: спарсит 10 кафе в Москве и сохранит в `test_results.csv`

### Вариант 2: Быстрый тест через скрипт

```bash
./test.sh
```

### Вариант 3: GUI (графический интерфейс)

```bash
./run_parser.sh
```

### Вариант 4: Командная строка

```bash
source venv/bin/activate
python3 Parser2gis.py -i "https://2gis.com/moscow/search/кафе" -o cafes.csv -f csv --parser.max_records 20
```

## 🔧 Важные настройки

### Для успешного парсинга:

1. **Увеличьте время ожидания** если мало результатов:
   - В коде: измените `time.sleep(5)` на `time.sleep(10)` в методе `parse_url()`
   - Или добавьте задержки: `--parser.delay_between_clicks 2000`

2. **Выключите headless режим** для отладки:
   - GUI: Настройки → Браузер → снять галочку "Скрытый режим"
   - CLI: `--chrome.headless no`

3. **Используйте прокси** если 2GIS блокирует:
   - Создайте прокси через SX.ORG в GUI
   - Или используйте файл: `--chrome.proxy_file proxies.txt`

## 🐛 Решение проблем

### Проблема: "Не найдено ни одной записи"

**Решение 1:** Запустите с видимым браузером
```bash
python3 Parser2gis.py -i "URL" -o test.csv -f csv --chrome.headless no
```

**Решение 2:** Проверьте URL
- ✓ Правильный: `https://2gis.com/moscow/search/кафе`
- ✗ Неправильный: `https://2gis.ru/...` (должно быть .com)

**Решение 3:** Увеличьте время ожидания
Отредактируйте строку ~1100 в `Parser2gis.py`:
```python
time.sleep(5)  # ← Измените на 10-15
```

### Проблема: "Chrome binary not found"

Установите Google Chrome:
https://www.google.com/chrome/

### Проблема: Парсит, но мало данных

1. Проверьте лимит: `--parser.max_records 100`
2. Убедитесь что URL содержит результаты
3. Попробуйте другой город/категорию

## 📁 Структура файлов

```
Parser2gis.py          - Основная программа
test_parser.py         - Тестовый скрипт
run_parser.sh          - Скрипт запуска GUI
test.sh                - Скрипт быстрого теста
README_Parser2gis.md   - Полная документация
QUICKSTART.md          - Этот файл
```

## 💡 Примеры команд

**Кафе в Москве (20 штук):**
```bash
python3 Parser2gis.py -i "https://2gis.com/moscow/search/кафе" -o cafes.csv -f csv --parser.max_records 20
```

**Аптеки в СПБ (50 штук, XLSX):**
```bash
python3 Parser2gis.py -i "https://2gis.com/spb/search/аптеки" -o pharmacies.xlsx -f xlsx --parser.max_records 50
```

**С прокси SX.ORG:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/магазины" \
  -o shops.csv -f csv \
  --chrome.proxy_method sxorg \
  --chrome.sxorg_api_key "ваш_ключ"
```

## 🎨 Создание прокси SX.ORG в GUI

1. Запустите программу: `./run_parser.sh`
2. Нажмите "Настройки"
3. Вкладка "Прокси"
4. Выберите "SX.ORG (Рекомендовано)"
5. Вставьте API-ключ и нажмите OK
6. Нажмите "Создать новый прокси SX.ORG"
7. Выберите параметры:
   - Страна: RU, US, etc.
   - Тип: Residential (лучше всего)
   - Протокол: HTTP/HTTPS
8. Нажмите "Создать"

## 📞 Техническая информация

**Версия:** 1.2.1

**Зависимости:**
- requests
- pydantic
- pychrome
- psutil
- openpyxl

**Требования:**
- Python 3.8+
- Google Chrome
- macOS / Linux / Windows

---

**Да, в оригинальном коде БЫЛА функция создания прокси SX.ORG** (`create_sxorg_proxy`), но не было GUI кнопки для её использования. Я добавил кнопку и полный диалог создания прокси! 🎉
