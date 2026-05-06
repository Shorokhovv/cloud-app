import os
import json
import datetime
import shutil
from flask import Flask, request, jsonify, send_file, render_template, url_for
from werkzeug.utils import secure_filename
from pathlib import Path

app = Flask(__name__)

# Конфигурация
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / 'storage'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'zip'}

# Создаем необходимые директории
STORAGE_DIR.mkdir(exist_ok=True)

def get_date_path():
    """Возвращает путь к подкаталогу по текущей дате"""
    return datetime.datetime.now().strftime('%Y/%m/%d')

def get_folder_path(folder_name=None):
    """Получает путь к папке в storage."""
    if folder_name:
        folder_name = secure_filename(folder_name)
        return STORAGE_DIR / folder_name
    return STORAGE_DIR / get_date_path()

def get_metadata_file(folder_path):
    return folder_path / 'metadata.json'

def load_folder_metadata(folder_path):
    """Загружает метаданные из metadata.json выбранной папки"""
    metadata_file = get_metadata_file(folder_path)
    if metadata_file.exists():
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_folder_metadata(folder_path, metadata):
    """Сохраняет метаданные в metadata.json выбранной папке"""
    metadata_file = get_metadata_file(folder_path)
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def gather_all_files():
    """Собирает метаданные из всех папок в storage."""
    files = []
    for path in STORAGE_DIR.rglob('metadata.json'):
        folder_path = path.parent
        metadata = load_folder_metadata(folder_path)
        relative_folder = str(folder_path.relative_to(STORAGE_DIR))
        for filename, info in metadata.items():
            files.append({
                'filename': filename,
                'original_name': info.get('original_name', filename),
                'size': info.get('size', 0),
                'size_formatted': info.get('size_formatted', 'Unknown'),
                'upload_date': info.get('upload_date', 'Unknown'),
                'folder': relative_folder,
                'is_image': info.get('is_image', False)
            })
    return files

def list_directories():
    """Возвращает список доступных директорий в storage"""
    directories = []
    for entry in STORAGE_DIR.iterdir():
        if entry.is_dir():
            directories.append(entry.name)
    return sorted(directories)

def allowed_file(filename):
    """Проверяет разрешен ли тип файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image(filename):
    """Проверяет, является ли файл изображением"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/')
def index():
    """Главная страница с формой загрузки"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Загружает файл на сервер"""
    # Проверяем наличие файла в запросе
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    # Проверяем выбрал ли пользователь файл
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        # Безопасное имя файла
        filename = secure_filename(file.filename)
        
        # Выбираем директорию для сохранения
        selected_folder = request.form.get('folder')
        if not selected_folder:
            return jsonify({'error': 'Folder is required'}), 400
        target_dir = get_folder_path(selected_folder)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Загружаем метаданные папки
        metadata = load_folder_metadata(target_dir)

        # Формируем полный путь для сохранения
        file_path = target_dir / filename

        # Если файл уже существует или имя занято в метаданных, добавляем timestamp
        while file_path.exists() or filename in metadata:
            name, ext = os.path.splitext(filename)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{name}_{timestamp}{ext}"
            file_path = target_dir / filename

        # Сохраняем файл
        file.save(file_path)

        # Сохраняем метаданные файла
        file_stat = file_path.stat()
        metadata[filename] = {
            'original_name': file.filename,
            'size': file_stat.st_size,
            'size_formatted': format_size(file_stat.st_size),
            'upload_date': datetime.datetime.now().isoformat(),
            'path': str(file_path.relative_to(BASE_DIR)),
            'is_image': is_image(filename)
        }

        save_folder_metadata(target_dir, metadata)
        
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'metadata': metadata[filename]
        }), 201
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/folders')
def folders():
    """Возвращает список доступных директорий"""
    return jsonify(list_directories())

@app.route('/create-folder', methods=['POST'])
def create_folder():
    """Создает новую директорию в storage"""
    folder_name = request.form.get('folder')
    if not folder_name:
        return jsonify({'error': 'Folder name is required'}), 400
    safe_name = secure_filename(folder_name)
    if not safe_name:
        return jsonify({'error': 'Invalid folder name'}), 400
    folder_path = STORAGE_DIR / safe_name
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=True)
    return jsonify({'message': f'Folder "{safe_name}" created successfully', 'folder': safe_name}), 201

@app.route('/delete-folder', methods=['POST'])
def delete_folder():
    """Удаляет директорию и все её содержимое"""
    folder_name = request.form.get('folder')
    if not folder_name:
        return jsonify({'error': 'Folder name is required'}), 400
    safe_name = secure_filename(folder_name)
    if not safe_name:
        return jsonify({'error': 'Invalid folder name'}), 400
    folder_path = STORAGE_DIR / safe_name
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    shutil.rmtree(folder_path)
    return jsonify({'message': f'Folder "{safe_name}" deleted successfully'}), 200

@app.route('/list')
def list_files():
    """Возвращает список файлов, опционально из одной папки"""
    selected_folder = request.args.get('folder')
    if selected_folder:
        folder_path = STORAGE_DIR / selected_folder
        if not folder_path.exists() or not folder_path.is_dir():
            return jsonify({'error': 'Folder not found'}), 404
        metadata = load_folder_metadata(folder_path)
        files_list = []
        for filename, info in metadata.items():
            files_list.append({
                'filename': filename,
                'original_name': info.get('original_name', filename),
                'size': info.get('size', 0),
                'size_formatted': info.get('size_formatted', 'Unknown'),
                'upload_date': info.get('upload_date', 'Unknown'),
                'folder': selected_folder,
                'is_image': info.get('is_image', False)
            })
    else:
        files_list = gather_all_files()

    files_list.sort(key=lambda x: x['upload_date'], reverse=True)
    return jsonify(files_list)

@app.route('/preview/<path:filename>')
def preview_file_fallback(filename):
    """Просмотр изображения без папки, если файл находится в одном из каталогов"""
    for path in STORAGE_DIR.rglob('metadata.json'):
        folder_path = path.parent
        metadata = load_folder_metadata(folder_path)
        if filename in metadata:
            if not is_image(filename):
                return jsonify({'error': 'Preview not available for this file type'}), 400
            file_info = metadata[filename]
            file_path = BASE_DIR / file_info['path']
            if not file_path.exists():
                return jsonify({'error': 'File not found on disk'}), 404
            return send_file(
                file_path,
                download_name=file_info.get('original_name', filename),
                as_attachment=False
            )
    return jsonify({'error': 'File not found'}), 404

@app.route('/preview/<path:folder>/<path:filename>')
def preview_file(folder, filename):
    """Просмотр изображения без скачивания"""
    folder_path = STORAGE_DIR / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    metadata = load_folder_metadata(folder_path)
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    if not is_image(filename):
        return jsonify({'error': 'Preview not available for this file type'}), 400
    file_info = metadata[filename]
    file_path = BASE_DIR / file_info['path']
    if not file_path.exists():
        return jsonify({'error': 'File not found on disk'}), 404
    return send_file(
        file_path,
        download_name=file_info.get('original_name', filename),
        as_attachment=False
    )

@app.route('/files/<path:folder>/<path:filename>')
def download_file(folder, filename):
    """Скачивает конкретный файл"""
    folder_path = STORAGE_DIR / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    metadata = load_folder_metadata(folder_path)
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    file_info = metadata[filename]
    file_path = BASE_DIR / file_info['path']
    if not file_path.exists():
        return jsonify({'error': 'File not found on disk'}), 404
    return send_file(
        file_path,
        download_name=file_info.get('original_name', filename),
        as_attachment=True
    )

@app.route('/files/info/<path:folder>/<path:filename>')
def file_info(folder, filename):
    """Возвращает информацию о конкретном файле"""
    folder_path = STORAGE_DIR / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    metadata = load_folder_metadata(folder_path)
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    return jsonify(metadata[filename])

@app.route('/delete/<path:folder>/<path:filename>', methods=['DELETE'])
def delete_file(folder, filename):
    """Удаляет файл из указанной папки"""
    folder_path = STORAGE_DIR / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    metadata = load_folder_metadata(folder_path)
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    file_info = metadata[filename]
    file_path = BASE_DIR / file_info['path']
    if file_path.exists():
        file_path.unlink()
    del metadata[filename]
    save_folder_metadata(folder_path, metadata)
    return jsonify({'message': f'File {filename} deleted successfully'})

def format_size(size):
    """Форматирует размер файла в человекочитаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)