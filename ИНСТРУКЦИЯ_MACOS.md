# 🍎 Инструкция по запуску Parser 2GIS на macOS

## Требования
- macOS 10.14 или новее
- Python 3.8 или выше
- Google Chrome (будет использоваться для парсинга)

## 📥 Установка

### Шаг 1: Проверка Python
Откройте **Terminal** и проверьте версию Python:
```bash
python3 --version
```
Должна быть версия 3.8 или выше. Если Python не установлен, скачайте с [python.org](https://www.python.org/downloads/)

### Шаг 2: Скачивание проекта
```bash
# Клонируйте репозиторий
git clone https://github.com/Inter1ark/Parser-2gis.git
cd Parser-2gis
```

Или скачайте ZIP-архив с GitHub и распакуйте его.

### Шаг 3: Создание виртуального окружения
```bash
python3 -m venv venv
```

### Шаг 4: Активация виртуального окружения
```bash
source venv/bin/activate
```

### Шаг 5: Установка зависимостей
```bash
pip install -r requirements.txt
```

## 🚀 Запуск

### Вариант 1: Через скрипт (рекомендуется)
```bash
chmod +x start_gui.sh
./start_gui.sh
```

### Вариант 2: Напрямую через Python
```bash
source venv/bin/activate
python3 Parser2gis.py
```

### Вариант 3: Через скрипт с параметрами командной строки
```bash
chmod +x run_parser.sh
./run_parser.sh --help
```

## 🔧 Использование

1. После запуска откроется графический интерфейс
2. Введите URL страницы 2GIS с результатами поиска
3. Настройте параметры парсинга (количество страниц, задержки и т.д.)
4. Нажмите "Начать парсинг"
5. Результаты сохранятся в CSV файл

## ⚠️ Возможные проблемы

### Chrome не найден
Убедитесь, что Google Chrome установлен в стандартной директории:
```
/Applications/Google Chrome.app
```

### Ошибка прав доступа
Если скрипт не запускается, дайте права на выполнение:
```bash
chmod +x start_gui.sh
chmod +x run_parser.sh
```

### Ошибка импорта модулей
Убедитесь, что виртуальное окружение активировано:
```bash
source venv/bin/activate
```

## 📝 Примечания

- При первом запуске Chrome может запросить разрешения
- Для парсинга больших объемов данных рекомендуется стабильное интернет-соединение
- Результаты сохраняются в директории проекта

## 🔄 Обновление

Для обновления до последней версии:
```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

---

**Поддержка:** [GitHub Issues](https://github.com/Inter1ark/Parser-2gis/issues)
