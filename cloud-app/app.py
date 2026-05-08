import os
import json
import datetime
import shutil
import secrets
import io
from flask import Flask, request, jsonify, send_file, render_template, url_for
from werkzeug.utils import secure_filename
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# Конфигурация
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / 'storage'

ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif',
    'doc', 'docx', 'xls', 'xlsx', 'zip',
    'mp4', 'mp3', 'webm', 'avi',
    'json', 'xml', 'csv',
    'ppt', 'pptx',
    'psd', 'ai', 'eps',
    'rar', '7z', 'tar', 'gz'
}

STORAGE_DIR.mkdir(exist_ok=True)

def get_date_path():
    return datetime.datetime.now().strftime('%Y/%m/%d')

def get_folder_path(folder_name=None):
    if folder_name:
        folder_name = secure_filename(folder_name)
        return STORAGE_DIR / folder_name
    return STORAGE_DIR / get_date_path()

def get_metadata_file(folder_path):
    return folder_path / 'metadata.json'

def load_folder_metadata(folder_path):
    metadata_file = get_metadata_file(folder_path)
    if metadata_file.exists():
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_folder_metadata(folder_path, metadata):
    metadata_file = get_metadata_file(folder_path)
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def gather_all_files():
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
    directories = []
    for entry in STORAGE_DIR.iterdir():
        if entry.is_dir():
            directories.append(entry.name)
    return sorted(directories)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def add_watermark(image_path, text="Photographer", opacity=0.3):
    """Накладывает полупрозрачный текст на изображение. Возвращает BytesIO."""
    img = Image.open(image_path).convert("RGBA")
    txt_layer = Image.new("RGBA", img.size, (255,255,255,0))
    draw = ImageDraw.Draw(txt_layer)
    try:
        font = ImageFont.truetype("arial.ttf", size=36)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0,0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    margin = 20
    position = (img.width - text_width - margin, img.height - text_height - margin)
    draw.text(position, text, font=font, fill=(255,255,255, int(255*opacity)))
    watermarked = Image.alpha_composite(img, txt_layer)
    if watermarked.mode == 'RGBA':
        watermarked = watermarked.convert('RGB')
    img_io = io.BytesIO()
    watermarked.save(img_io, format='JPEG', quality=85)
    img_io.seek(0)
    return img_io

# Управление доступом
ACCESS_FILE = STORAGE_DIR / 'access.json'

def load_access():
    if ACCESS_FILE.exists():
        with open(ACCESS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_access(data):
    with open(ACCESS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        selected_folder = request.form.get('folder')
        target_dir = get_folder_path(selected_folder)
        target_dir.mkdir(parents=True, exist_ok=True)
        metadata = load_folder_metadata(target_dir)
        file_path = target_dir / filename
        while file_path.exists() or filename in metadata:
            name, ext = os.path.splitext(filename)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{name}_{timestamp}{ext}"
            file_path = target_dir / filename
        file.save(file_path)
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
    return jsonify(list_directories())

@app.route('/create-folder', methods=['POST'])
def create_folder():
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
    # Также удаляем запись из access.json при удалении папки
    access = load_access()
    if safe_name in access:
        del access[safe_name]
        save_access(access)
    return jsonify({'message': f'Folder "{safe_name}" deleted successfully'}), 200

@app.route('/list')
def list_files():
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

@app.route('/preview/<path:folder>/<path:filename>')
def preview_file(folder, filename):
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
    watermark = request.args.get('watermark', '0') == '1'
    if watermark:
        return send_file(
            add_watermark(file_path),
            mimetype='image/jpeg',
            download_name=file_info.get('original_name', filename),
            as_attachment=False
        )
    return send_file(
        file_path,
        download_name=file_info.get('original_name', filename),
        as_attachment=False
    )

@app.route('/files/<path:folder>/<path:filename>')
def download_file(folder, filename):
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
    watermark = request.args.get('watermark', '0') == '1'
    if watermark and is_image(filename):
        return send_file(
            add_watermark(file_path),
            mimetype='image/jpeg',
            download_name=file_info.get('original_name', filename),
            as_attachment=True
        )
    return send_file(
        file_path,
        download_name=file_info.get('original_name', filename),
        as_attachment=True
    )

@app.route('/files/info/<path:folder>/<path:filename>')
def file_info(folder, filename):
    folder_path = STORAGE_DIR / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    metadata = load_folder_metadata(folder_path)
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    return jsonify(metadata[filename])

@app.route('/delete/<path:folder>/<path:filename>', methods=['DELETE'])
def delete_file(folder, filename):
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

# ---------- Маршруты доступа ----------
@app.route('/generate-access', methods=['POST'])
def generate_access():
    folder = request.form.get('folder')
    password = request.form.get('password', '')
    if not folder or not (STORAGE_DIR / folder).is_dir():
        return jsonify({'error': 'Invalid folder'}), 400
    token = secrets.token_urlsafe(16)
    access = load_access()
    access[folder] = {'token': token, 'password': password}
    save_access(access)

    if 'X-Forwarded-Host' in request.headers:
        host = request.headers['X-Forwarded-Host']
    else:
        host = request.host
    scheme = request.headers.get('X-Forwarded-Proto', 'http')
    gallery_url = f"{scheme}://{host}/gallery/{token}"

    return jsonify({'message': 'Access granted', 'token': token, 'url': gallery_url})
@app.route('/revoke-access', methods=['POST'])
def revoke_access():
    folder = request.form.get('folder')
    if not folder:
        return jsonify({'error': 'Folder required'}), 400
    access = load_access()
    if folder in access:
        del access[folder]
        save_access(access)
    return jsonify({'message': 'Access revoked'})

@app.route('/gallery/<token>')
def client_gallery(token):
    access = load_access()
    folder = None
    for f, data in access.items():
        if data['token'] == token:
            folder = f
            break
    if not folder or not (STORAGE_DIR / folder).is_dir():
        return "Ссылка недействительна", 404
    # Здесь можно добавить проверку пароля через отдельную форму, если нужен пароль.
    # Пока просто показываем галерею (пароль не проверяется, но хранится).
    return render_template('gallery.html', folder=folder, token=token)

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)