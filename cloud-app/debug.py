import os
import sys
from pathlib import Path

print("=== ТЕКУЩАЯ ДИРЕКТОРИЯ ===")
print(f"Текущая директория: {os.getcwd()}")
print(f"Содержимое текущей директории: {os.listdir('.')}")

print("\n=== ПРОВЕРКА ПАПКИ TEMPLATES ===")
templates_path = Path('templates')
print(f"Папка templates существует: {templates_path.exists()}")
if templates_path.exists():
    print(f"Содержимое папки templates: {os.listdir('templates')}")
else:
    print("Папка templates НЕ найдена!")

print("\n=== АБСОЛЮТНЫЕ ПУТИ ===")
abs_templates = Path.cwd() / 'templates'
print(f"Абсолютный путь к templates: {abs_templates}")
print(f"Существует: {abs_templates.exists()}")

print("\n=== ПОИСК index.html ===")
if templates_path.exists():
    index_file = templates_path / 'index.html'
    print(f"Файл index.html существует: {index_file.exists()}")
    if index_file.exists():
        print(f"Размер файла: {index_file.stat().st_size} байт")
else:
    print("Невозможно проверить index.html - нет папки templates")
