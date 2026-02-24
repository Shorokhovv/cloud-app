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
METADATA_FILE = BASE_DIR / 'metadata.json'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'zip'}

# Создаем необходимые директории
STORAGE_DIR.mkdir(exist_ok=True)

def load_metadata():
    """Загружает метаданные из файла"""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_metadata(metadata):
    """Сохраняет метаданные в файл"""
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def get_date_path():
    """Возвращает путь к подкаталогу по текущей дате"""
    return datetime.datetime.now().strftime('%Y/%m/%d')

def ensure_date_directory():
    """Создает структуру каталогов по дате"""
    date_path = STORAGE_DIR / get_date_path()
    date_path.mkdir(parents=True, exist_ok=True)
    return date_path

def allowed_file(filename):
    """Проверяет разрешен ли тип файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        
        # Создаем структуру по дате
        date_path = ensure_date_directory()
        
        # Формируем полный путь для сохранения
        file_path = date_path / filename
        
        # Если файл уже существует, добавляем timestamp
        if file_path.exists():
            name, ext = os.path.splitext(filename)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{name}_{timestamp}{ext}"
            file_path = date_path / filename
        
        # Сохраняем файл
        file.save(file_path)
        
        # Загружаем и обновляем метаданные
        metadata = load_metadata()
        
        # Сохраняем метаданные файла
        file_stat = file_path.stat()
        metadata[filename] = {
            'original_name': file.filename,
            'size': file_stat.st_size,
            'size_formatted': format_size(file_stat.st_size),
            'upload_date': datetime.datetime.now().isoformat(),
            'path': str(file_path.relative_to(BASE_DIR)),
            'date_folder': get_date_path()
        }
        
        save_metadata(metadata)
        
        # Для API запросов возвращаем JSON
        if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
            return jsonify({
                'message': 'File uploaded successfully',
                'filename': filename,
                'metadata': metadata[filename]
            }), 201
        else:
            # Для формы возвращаем HTML
            return render_template('index.html', success=f"File {filename} uploaded successfully!")
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/list')
def list_files():
    """Возвращает список всех загруженных файлов"""
    metadata = load_metadata()
    
    # Преобразуем метаданные в список для удобства
    files_list = []
    for filename, info in metadata.items():
        files_list.append({
            'filename': filename,
            'original_name': info.get('original_name', filename),
            'size': info.get('size', 0),
            'size_formatted': info.get('size_formatted', 'Unknown'),
            'upload_date': info.get('upload_date', 'Unknown'),
            'download_url': url_for('download_file', filename=filename, _external=True)
        })
    
    # Сортируем по дате загрузки (новые сначала)
    files_list.sort(key=lambda x: x['upload_date'], reverse=True)
    
    return jsonify(files_list)

@app.route('/files/<path:filename>')
def download_file(filename):
    """Скачивает конкретный файл"""
    metadata = load_metadata()
    
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

@app.route('/files/info/<filename>')
def file_info(filename):
    """Возвращает информацию о конкретном файле"""
    metadata = load_metadata()
    
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    
    return jsonify(metadata[filename])

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Удаляет файл (дополнительная функция)"""
    metadata = load_metadata()
    
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    
    file_info = metadata[filename]
    file_path = BASE_DIR / file_info['path']
    
    # Удаляем файл
    if file_path.exists():
        file_path.unlink()
    
    # Удаляем из метаданных
    del metadata[filename]
    save_metadata(metadata)
    
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