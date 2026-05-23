import os
import json
import datetime
import shutil
import secrets
import io
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

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

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
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

# ---------- ВОДЯНОЙ ЗНАК (Двач-стиль) ----------
def add_watermark(image_path, text="Shorokhovv", opacity=0.5):
    try:
        img = Image.open(image_path).convert("RGBA")
        txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)

        # Попытка загрузить жирный шрифт
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            base_font = ImageFont.truetype(font_path, size=10)
        except:
            base_font = ImageFont.load_default()

        target_width = img.width - 40
        # Если шрифт - стандартный, не масштабируем
        if hasattr(base_font, 'getsize') or True:  # Для надёжности подберём размер
            # Определяем оптимальный размер шрифта, чтобы текст вписался в ширину
            size = 10
            best_size = 10
            best_font = base_font
            # Начинаем с 10 и увеличиваем, пока ширина не превысит допустимую
            while True:
                font = ImageFont.truetype(font_path, size=size) if 'font_path' in dir() else base_font
                bbox = draw.textbbox((0,0), text, font=font)
                tw = bbox[2] - bbox[0]
                if tw > target_width:
                    break
                best_size = size
                best_font = font
                size += 2

            font = best_font
        else:
            font = base_font

        bbox = draw.textbbox((0,0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (img.width - tw) // 2
        y = (img.height - th) // 2

        # Чёрная обводка и белый полупрозрачный текст
        offsets = [(-1,-1), (-1,1), (1,-1), (1,1)]
        for dx, dy in offsets:
            draw.text((x+dx, y+dy), text, font=font, fill=(0,0,0,255))
        draw.text((x, y), text, font=font, fill=(255,255,255, int(255*opacity)))

        watermarked = Image.alpha_composite(img, txt_layer).convert("RGB")
        img_io = io.BytesIO()
        watermarked.save(img_io, format='JPEG', quality=85)
        img_io.seek(0)
        print(f"✓ Watermark наложен: {image_path}")
        return img_io

    except Exception as e:
        print(f"Ошибка watermark: {e}")
        with open(image_path, 'rb') as f:
            img_io = io.BytesIO(f.read())
        img_io.seek(0)
        return img_io

# ---------- УПРАВЛЕНИЕ ДОСТУПОМ ----------
ACCESS_FILE = STORAGE_DIR / 'access.json'

def load_access():
    if ACCESS_FILE.exists():
        with open(ACCESS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_access(data):
    with open(ACCESS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ---------- МАРШРУТЫ ----------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    files = request.files.getlist('file')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No selected file'}), 400

    selected_folder = request.form.get('folder')
    target_dir = get_folder_path(selected_folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata = load_folder_metadata(target_dir)

    uploaded = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
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
            uploaded.append({
                'filename': filename,
                'original_name': file.filename,
                'size_formatted': format_size(file_stat.st_size)
            })

    save_folder_metadata(target_dir, metadata)

    if not uploaded:
        return jsonify({'error': 'No valid files uploaded'}), 400

    return jsonify({'message': f'Uploaded {len(uploaded)} file(s)', 'files': uploaded}), 201

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
    return jsonify({'message': f'Folder "{safe_name}" created', 'folder': safe_name}), 201

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
    access = load_access()
    if safe_name in access:
        del access[safe_name]
        save_access(access)
    return jsonify({'message': f'Folder "{safe_name}" deleted'}), 200

@app.route('/list')
def list_files():
    selected_folder = request.args.get('folder')
    if not selected_folder:
        return jsonify([])
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
        return jsonify({'error': 'Preview not available'}), 400
    file_info = metadata[filename]
    file_path = BASE_DIR / file_info['path']
    if not file_path.exists():
        return jsonify({'error': 'File not found on disk'}), 404
    return send_file(file_path, download_name=file_info.get('original_name', filename), as_attachment=False)

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
    return send_file(file_path, download_name=file_info.get('original_name', filename), as_attachment=True)

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
    return jsonify({'message': f'File {filename} deleted'})

# ---------- БЕЗОПАСНЫЙ ПРЕДПРОСМОТР С ВОДЯНЫМ ЗНАКОМ ----------
@app.route('/secure-preview/<path:folder>/<path:filename>')
def secure_preview(folder, filename):
    token = request.args.get('token', '')
    access = load_access()
    folder_found = None
    for f, data in access.items():
        if data['token'] == token:
            folder_found = f
            break
    if not folder_found or folder_found != folder:
        return jsonify({'error': 'Access denied'}), 403

    folder_path = STORAGE_DIR / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({'error': 'Folder not found'}), 404
    metadata = load_folder_metadata(folder_path)
    if filename not in metadata:
        return jsonify({'error': 'File not found'}), 404
    if not is_image(filename):
        return jsonify({'error': 'Preview not available'}), 400

    file_info = metadata[filename]
    file_path = BASE_DIR / file_info['path']
    if not file_path.exists():
        return jsonify({'error': 'File not found on disk'}), 404

    return send_file(
        add_watermark(file_path, text="Shorokhovv", opacity=0.5),
        mimetype='image/jpeg',
        download_name=file_info.get('original_name', filename),
        as_attachment=False
    )

# ---------- ГЕНЕРАЦИЯ ДОСТУПА ----------
@app.route('/generate-access', methods=['POST'])
def generate_access():
    try:
        folder = request.form.get('folder')
        password = request.form.get('password', '')
        if not folder or not (STORAGE_DIR / folder).is_dir():
            return jsonify({'error': 'Invalid folder'}), 400
        token = secrets.token_urlsafe(16)
        access = load_access()
        access[folder] = {
            'token': token,
            'password': password,
            'failed_attempts': 0,
            'is_blocked': False
        }
        save_access(access)
        if 'X-Forwarded-Host' in request.headers:
            host = request.headers['X-Forwarded-Host']
        else:
            host = request.host
        scheme = request.headers.get('X-Forwarded-Proto', 'http')
        gallery_url = f"{scheme}://{host}/gallery/{token}"
        print(f"Сгенерирована ссылка: {gallery_url}")
        return jsonify({'message': 'Access granted', 'token': token, 'url': gallery_url})
    except Exception as e:
        print(f"Ошибка в generate_access: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/list-access')
def list_access():
    access = load_access()
    result = []
    for folder, data in access.items():
        result.append({
            'folder': folder,
            'token': data.get('token', ''),
            'password': data.get('password', ''),
            'is_blocked': data.get('is_blocked', False),
            'failed_attempts': data.get('failed_attempts', 0)
        })
    return jsonify(result)

@app.route('/verify-password', methods=['POST'])
def verify_password():
    token = request.form.get('token', '')
    password = request.form.get('password', '')
    access = load_access()
    folder = None
    for f, data in access.items():
        if data.get('token') == token:
            folder = f
            break
    if not folder:
        return jsonify({'error': 'Invalid token'}), 403
    access_data = access[folder]
    if access_data.get('is_blocked'):
        return jsonify({'error': 'Access blocked', 'blocked': True}), 403
    correct_password = access_data.get('password', '')
    if not correct_password:
        return jsonify({'success': True})
    if password == correct_password:
        access_data['failed_attempts'] = 0
        save_access(access)
        return jsonify({'success': True})
    else:
        access_data['failed_attempts'] = access_data.get('failed_attempts', 0) + 1
        if access_data['failed_attempts'] >= 5:
            access_data['is_blocked'] = True
            print(f"Токен для папки '{folder}' заблокирован после 5 неправильных попыток")
        save_access(access)
        return jsonify({
            'success': False,
            'attempts_left': max(0, 5 - access_data['failed_attempts']),
            'blocked': access_data.get('is_blocked', False)
        })

@app.route('/revoke-access', methods=['POST'])
def revoke_access():
    token = request.form.get('token')
    if not token:
        return jsonify({'error': 'Token required'}), 400
    access = load_access()
    folder_to_delete = None
    for f, data in access.items():
        if data.get('token') == token:
            folder_to_delete = f
            break
    if folder_to_delete:
        del access[folder_to_delete]
        save_access(access)
        return jsonify({'message': 'Access revoked'})
    return jsonify({'error': 'Token not found'}), 404

@app.route('/gallery/<token>')
def client_gallery(token):
    access = load_access()
    folder = None
    for f, data in access.items():
        if data.get('token') == token:
            folder = f
            break
    if not folder or not (STORAGE_DIR / folder).is_dir():
        return "Ссылка недействительна", 404
    return render_template('gallery.html', folder=folder, token=token)

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)