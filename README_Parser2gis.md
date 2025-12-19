# Parser 2GIS - Парсер данных 2GIS
## Что изменилось
Программа теперь **реально парсит** данные с 2GIS вместо имитации:
### Основные изменения:
1. **Класс `Parser2GIS`** - реальный движок парсинга с использованием Chrome DevTools Protocol
2. **Класс `Writer`** - сохранение данных в CSV, XLSX, JSON форматах
3. **Класс `ChromeRemote`** - улучшенное управление браузером с навигацией и взаимодействием
4. **Извлечение данных**:
   - Из API ответов 2GIS (catalog/branch/list, catalog/geo/search)
   - Из HTML контента страницы
   - Автоматическая прокрутка для загрузки дополнительных элементов
### Что парсится:
- ID организации
- Название
- Адрес
- Телефоны
- Сайты
- Email
- GPS координаты (широта, долгота)
- Рубрики
- URL на странице 2GIS
## Установка
### 1. Создайте виртуальное окружение (если еще не создано):
```bash
cd /Users/nonnakomissarova/Downloads
python3 -m venv venv
```
### 2. Активируйте виртуальное окружение:
```bash
source venv/bin/activate
```
### 3. Установите зависимости:
```bash
pip install requests pydantic pychrome psutil openpyxl
```
### 4. Убедитесь, что Google Chrome установлен на вашем Mac
Программа автоматически найдет Chrome по стандартному пути:
- `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
## Использование
### Запуск с GUI (графический интерфейс):
```bash
source venv/bin/activate
python3 Parser2gis.py
```
### Запуск из командной строки:
```bash
source venv/bin/activate
python3 Parser2gis.py -i "https://2gis.com/moscow/search/кафе" -o results.csv -f csv
```
### Примеры команд:
**Парсинг кафе в Москве в CSV:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/кафе" \
  -o cafe_moscow.csv \
  -f csv
```
**Парсинг в XLSX с ограничением в 50 записей:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/spb/search/рестораны" \
  -o restaurants.xlsx \
  -f xlsx \
  --parser.max_records 50
```
**Парсинг нескольких категорий:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/кафе" \
     "https://2gis.com/moscow/search/рестораны" \
  -o food_moscow.csv \
  -f csv
```
**С использованием прокси:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/магазины" \
  -o shops.csv \
  -f csv \
  --chrome.proxy_file proxies.txt
```
## Настройки
### Основные параметры:
- `-i, --url` - URL страниц для парсинга (можно несколько)
- `-o, --output-path` - путь к файлу результатов
- `-f, --format` - формат вывода: csv, xlsx, json
### Параметры браузера:
- `--chrome.headless yes` - скрытый режим (без отображения окна)
- `--chrome.disable_images yes` - отключить загрузку изображений (быстрее)
- `--chrome.proxy_file PATH` - файл с прокси серверами
### Параметры парсера:
- `--parser.max_records N` - максимальное количество записей (по умолчанию 100000)
- `--parser.delay_between_clicks MS` - задержка между кликами в миллисекундах
- `--parser.skip_404_response yes` - пропускать страницы с ошибкой 404
### Параметры вывода:
- `--writer.csv.add_rubrics yes` - добавить колонку "Рубрики"
- `--writer.csv.remove_duplicates yes` - удалить дубликаты
- `--writer.csv.remove_empty_columns yes` - удалить пустые колонки
## Формат файла прокси (proxies.txt)
Формат 1 (IP:PORT):
```
123.45.67.89:8080
98.76.54.32:3128
```
Формат 2 (IP:PORT:USER:PASS):
```
123.45.67.89:8080:username:password
98.76.54.32:3128:user2:pass2
```
## Поддержка SX.ORG прокси
Программа поддерживает интеграцию с сервисом SX.ORG для автоматического получения прокси:
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/аптеки" \
  -o pharmacies.csv \
  -f csv \
  --chrome.proxy_method sxorg \
  --chrome.sxorg_api_key "ваш_api_ключ" \
  --chrome.sxorg_country RU
```
## Структура выходных данных
### CSV/XLSX формат:
| ID | Название | Адрес | Телефон | Сайт | Email | URL | Широта | Долгота | Рубрики |
|----|----------|-------|---------|------|-------|-----|--------|---------|---------|
| 123456 | Кафе "Пример" | ул. Ленина, 1 | +7(495)123-45-67 | example.ru | info@example.ru | https://2gis.com/firm/123456 | 55.7558 | 37.6173 | Кафе, Общепит |
### JSON формат:
```json
[
  {
    "id": "123456",
    "name": "Кафе \"Пример\"",
    "address_name": "ул. Ленина, 1",
    "contact_groups": [
      {
        "contacts": [
          {"type": "phone", "value": "+7(495)123-45-67"}
        ]
      }
    ],
    "point": {
      "lat": 55.7558,
      "lon": 37.6173
    },
    "rubrics": [
      {"name": "Кафе"}
    ]
  }
]
```
## Решение проблем
### Ошибка "Chrome binary not found":
Убедитесь, что Google Chrome установлен. Если Chrome установлен в нестандартной директории, укажите путь:
```bash
--chrome.binary_path "/путь/к/Google Chrome"
```
### Парсер ничего не находит:
1. Проверьте правильность URL
2. Попробуйте увеличить задержки: `--parser.delay_between_clicks 1000`
3. Запустите без headless режима, чтобы видеть, что происходит
4. Проверьте логи в GUI или консоли
### Медленная работа:
1. Используйте `--chrome.disable_images yes`
2. Используйте `--chrome.headless yes`
3. Уменьшите `--parser.max_records`
## Логи
Логи сохраняются в GUI режиме в окне программы. В CLI режиме выводятся в консоль.
Уровень логирования можно настроить в GUI через Настройки или в конфиге.
## Автор
Версия: 1.2.1
---
**Важно**: Используйте парсер ответственно и в соответствии с правилами 2GIS и законодательством.
# Parser 2GIS - Парсер данных 2GIS

## Что изменилось

Программа теперь **реально парсит** данные с 2GIS вместо имитации:

### Основные изменения:
1. **Класс `Parser2GIS`** - реальный движок парсинга с использованием Chrome DevTools Protocol
2. **Класс `Writer`** - сохранение данных в CSV, XLSX, JSON форматах
3. **Класс `ChromeRemote`** - улучшенное управление браузером с навигацией и взаимодействием
4. **Извлечение данных**:
   - Из API ответов 2GIS (catalog/branch/list, catalog/geo/search)
   - Из HTML контента страницы
   - Автоматическая прокрутка для загрузки дополнительных элементов

### Что парсится:
- ID организации
- Название
- Адрес
- Телефоны
- Сайты
- Email
- GPS координаты (широта, долгота)
- Рубрики
- URL на странице 2GIS

## Установка

### 1. Создайте виртуальное окружение (если еще не создано):
```bash
cd /Users/nonnakomissarova/Downloads
python3 -m venv venv
```

### 2. Активируйте виртуальное окружение:
```bash
source venv/bin/activate
```

### 3. Установите зависимости:
```bash
pip install requests pydantic pychrome psutil openpyxl
```

### 4. Убедитесь, что Google Chrome установлен на вашем Mac
Программа автоматически найдет Chrome по стандартному пути:
- `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`

## Использование

### Запуск с GUI (графический интерфейс):
```bash
source venv/bin/activate
python3 Parser2gis.py
```

### Запуск из командной строки:
```bash
source venv/bin/activate
python3 Parser2gis.py -i "https://2gis.com/moscow/search/кафе" -o results.csv -f csv
```

### Примеры команд:

**Парсинг кафе в Москве в CSV:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/кафе" \
  -o cafe_moscow.csv \
  -f csv
```

**Парсинг в XLSX с ограничением в 50 записей:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/spb/search/рестораны" \
  -o restaurants.xlsx \
  -f xlsx \
  --parser.max_records 50
```

**Парсинг нескольких категорий:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/кафе" \
     "https://2gis.com/moscow/search/рестораны" \
  -o food_moscow.csv \
  -f csv
```

**С использованием прокси:**
```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/магазины" \
  -o shops.csv \
  -f csv \
  --chrome.proxy_file proxies.txt
```

## Настройки

### Основные параметры:
- `-i, --url` - URL страниц для парсинга (можно несколько)
- `-o, --output-path` - путь к файлу результатов
- `-f, --format` - формат вывода: csv, xlsx, json

### Параметры браузера:
- `--chrome.headless yes` - скрытый режим (без отображения окна)
- `--chrome.disable_images yes` - отключить загрузку изображений (быстрее)
- `--chrome.proxy_file PATH` - файл с прокси серверами

### Параметры парсера:
- `--parser.max_records N` - максимальное количество записей (по умолчанию 100000)
- `--parser.delay_between_clicks MS` - задержка между кликами в миллисекундах
- `--parser.skip_404_response yes` - пропускать страницы с ошибкой 404

### Параметры вывода:
- `--writer.csv.add_rubrics yes` - добавить колонку "Рубрики"
- `--writer.csv.remove_duplicates yes` - удалить дубликаты
- `--writer.csv.remove_empty_columns yes` - удалить пустые колонки

## Формат файла прокси (proxies.txt)

Формат 1 (IP:PORT):
```
123.45.67.89:8080
98.76.54.32:3128
```

Формат 2 (IP:PORT:USER:PASS):
```
123.45.67.89:8080:username:password
98.76.54.32:3128:user2:pass2
```

## Поддержка SX.ORG прокси

Программа поддерживает интеграцию с сервисом SX.ORG для автоматического получения прокси:

```bash
python3 Parser2gis.py \
  -i "https://2gis.com/moscow/search/аптеки" \
  -o pharmacies.csv \
  -f csv \
  --chrome.proxy_method sxorg \
  --chrome.sxorg_api_key "ваш_api_ключ" \
  --chrome.sxorg_country RU
```

## Структура выходных данных

### CSV/XLSX формат:
| ID | Название | Адрес | Телефон | Сайт | Email | URL | Широта | Долгота | Рубрики |
|----|----------|-------|---------|------|-------|-----|--------|---------|---------|
| 123456 | Кафе "Пример" | ул. Ленина, 1 | +7(495)123-45-67 | example.ru | info@example.ru | https://2gis.com/firm/123456 | 55.7558 | 37.6173 | Кафе, Общепит |

### JSON формат:
```json
[
  {
    "id": "123456",
    "name": "Кафе \"Пример\"",
    "address_name": "ул. Ленина, 1",
    "contact_groups": [
      {
        "contacts": [
          {"type": "phone", "value": "+7(495)123-45-67"}
        ]
      }
    ],
    "point": {
      "lat": 55.7558,
      "lon": 37.6173
    },
    "rubrics": [
      {"name": "Кафе"}
    ]
  }
]
```

## Решение проблем

### Ошибка "Chrome binary not found":
Убедитесь, что Google Chrome установлен. Если Chrome установлен в нестандартной директории, укажите путь:
```bash
--chrome.binary_path "/путь/к/Google Chrome"
```

### Парсер ничего не находит:
1. Проверьте правильность URL
2. Попробуйте увеличить задержки: `--parser.delay_between_clicks 1000`
3. Запустите без headless режима, чтобы видеть, что происходит
4. Проверьте логи в GUI или консоли

### Медленная работа:
1. Используйте `--chrome.disable_images yes`
2. Используйте `--chrome.headless yes`
3. Уменьшите `--parser.max_records`

## Логи

Логи сохраняются в GUI режиме в окне программы. В CLI режиме выводятся в консоль.

Уровень логирования можно настроить в GUI через Настройки или в конфиге.

## Автор

Версия: 1.2.1

---

**Важно**: Используйте парсер ответственно и в соответствии с правилами 2GIS и законодательством.
