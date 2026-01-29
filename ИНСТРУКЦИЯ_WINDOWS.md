# 🪟 Инструкция по запуску Parser 2GIS на Windows

## Требования
- Windows 10 или новее
- Python 3.8 или выше
- Google Chrome (будет использоваться для парсинга)

## 📥 Установка

### Шаг 1: Установка Python
1. Скачайте Python с [python.org](https://www.python.org/downloads/)
2. При установке **обязательно** отметьте галочку "Add Python to PATH"
3. Проверьте установку, открыв **Command Prompt** (cmd):
```cmd
python --version
```

### Шаг 2: Скачивание проекта
**Вариант A: Через Git**
```cmd
git clone https://github.com/Inter1ark/Parser-2gis.git
cd Parser-2gis
```

**Вариант B: Скачать ZIP**
1. Перейдите на https://github.com/Inter1ark/Parser-2gis
2. Нажмите зелёную кнопку "Code" → "Download ZIP"
3. Распакуйте архив в удобную папку
4. Откройте Command Prompt в этой папке

### Шаг 3: Создание виртуального окружения
```cmd
python -m venv venv
```

### Шаг 4: Активация виртуального окружения
```cmd
venv\Scripts\activate
```
После активации в начале строки появится `(venv)`

### Шаг 5: Установка зависимостей
```cmd
pip install -r requirements.txt
```

## 🚀 Запуск

### Вариант 1: Через bat-файл (самый простой)
Дважды кликните на файл **start_gui.bat** в проводнике

### Вариант 2: Через командную строку
```cmd
venv\Scripts\activate
python Parser2gis.py
```

### Вариант 3: Через PowerShell
```powershell
.\venv\Scripts\Activate.ps1
python Parser2gis.py
```

> ⚠️ **Примечание:** Если PowerShell блокирует выполнение скриптов, выполните:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

## 🔧 Использование

1. После запуска откроется окно программы
2. Введите URL страницы 2GIS с результатами поиска
   - Пример: `https://2gis.ru/moscow/search/кафе`
3. Настройте параметры:
   - Количество страниц для парсинга
   - Задержки между запросами
   - Использование прокси (опционально)
4. Нажмите кнопку "Начать парсинг"
5. Дождитесь завершения (прогресс отображается в окне)
6. Результаты автоматически сохранятся в CSV файл

## ⚠️ Возможные проблемы и решения

### Python не найден
- Переустановите Python с галочкой "Add to PATH"
- Или используйте `py` вместо `python`:
  ```cmd
  py -m venv venv
  ```

### Chrome не найден
Убедитесь, что Google Chrome установлен по стандартному пути:
```
C:\Program Files\Google\Chrome\Application\chrome.exe
```
или
```
C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
```

### Ошибка "venv\Scripts\activate не является внутренней командой"
Убедитесь, что вы находитесь в папке проекта:
```cmd
cd путь\к\Parser-2gis
```

### Ошибки импорта модулей
Убедитесь, что виртуальное окружение активировано:
```cmd
venv\Scripts\activate
```
Переустановите зависимости:
```cmd
pip install -r requirements.txt --force-reinstall
```

### Антивирус блокирует работу
Добавьте папку проекта в исключения антивируса

### Ошибка "Access Denied" при активации venv
Запустите Command Prompt от имени администратора

## 📁 Структура файлов

```
Parser-2gis/
├── Parser2gis.py          # Основной файл программы
├── start_gui.bat          # Скрипт быстрого запуска
├── requirements.txt       # Список зависимостей
├── venv/                  # Виртуальное окружение (создаётся при установке)
└── результаты.csv         # Файл с результатами (создаётся после парсинга)
```

## 📝 Полезные советы

1. **Стабильное подключение к интернету** - важно для бесперебойной работы
2. **Не закрывайте окно Chrome** - оно открывается автоматически для парсинга
3. **Большие объёмы данных** - парсинг может занять продолжительное время
4. **Резервное копирование** - CSV файлы создаются автоматически с датой/временем

## 🔄 Обновление программы

```cmd
git pull origin main
venv\Scripts\activate
pip install -r requirements.txt --upgrade
```

## 🆘 Получить помощь

Если возникли проблемы:
1. Проверьте раздел "Возможные проблемы" выше
2. Создайте Issue на GitHub: https://github.com/Inter1ark/Parser-2gis/issues
3. Приложите текст ошибки и скриншот

---

**Версия:** 1.2.1  
**Поддержка:** [GitHub Issues](https://github.com/Inter1ark/Parser-2gis/issues)
