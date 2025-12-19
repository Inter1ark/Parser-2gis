# Parser2GIS

## Описание
Парсер организаций 2GIS с поддержкой headless Chrome, SX.ORG прокси, GUI на Tkinter.

## Быстрый старт
1. Установите Python 3.10+ и Chrome.
2. Установите зависимости:
   ```
   pip install -r requirements.txt
   ```
3. Запуск:
   - Windows: `start_gui.bat` или `python Parser2gis.py`
   - Mac/Linux: `./start_gui.sh` или `python3 Parser2gis.py`

## Компиляция EXE (Windows)
1. Установите pyinstaller:
   ```
   pip install pyinstaller
   ```
2. Соберите exe с иконкой:
   ```
   pyinstaller --onefile --windowed --icon=logo.png Parser2gis.py
   ```
3. В папке `dist/` появится готовый exe-файл.

## Логотип
- Файл `logo.png` используется как иконка программы и установщика.

## Документация
- Подробнее: README_Parser2gis.md, QUICKSTART.md

## Лицензия
MIT
