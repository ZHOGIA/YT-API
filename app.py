from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import io
from PIL import Image
from rembg import remove, new_session
import onnxruntime as ort
import downloader
import os
import threading
import time

app = Flask(__name__)
CORS(app)

# --- AUTO HARDWARE DETECTION ---
def get_best_provider():
    try:
        available = ort.get_available_providers()
        print(f"[*] Hardware terdeteksi: {available}")
        
        if 'CUDAExecutionProvider' in available:
            print("[+] Menggunakan NVIDIA CUDA untuk rendering.")
            return ['CUDAExecutionProvider']
        
        if 'DmlExecutionProvider' in available:
            print("[+] Menggunakan DirectML (AMD/Intel GPU) untuk rendering.")
            return ['DmlExecutionProvider']
        
        print("[!] Menggunakan CPU untuk rendering (Paling lambat tapi stabil).")
        return ['CPUExecutionProvider']
    except Exception as e:
        print(f"[X] Gagal mendeteksi provider: {e}")
        return ['CPUExecutionProvider']

try:
    best_providers = get_best_provider()
    session = new_session("u2net", providers=best_providers)
    print("[*] Model AI berhasil dimuat!")
except Exception as e:
    print(f"[X] Gagal inisialisasi hardware spesifik: {e}")
    session = new_session("u2net")

@app.route('/')
def index():
    return jsonify({"status": "ok", "message": "Backend API is running!"})

@app.route('/api/info', methods=['POST'])
def get_info():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        info = downloader.get_info(url)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/process', methods=['POST'])
def process():
    data = request.json
    url = data.get('url')
    format_type = data.get('format') # 'mp3' or 'mp4'
    quality = data.get('quality') # format_id or string
    
    if not url or not format_type:
        return jsonify({"error": "Missing parameters"}), 400
        
    task_id = downloader.start_download(url, format_type, quality)
    return jsonify({"task_id": task_id})

@app.route('/api/status/<task_id>', methods=['GET'])
def status(task_id):
    task = downloader.get_task_status(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)

@app.route('/api/download/<task_id>', methods=['GET'])
def download(task_id):
    task = downloader.get_task_status(task_id)
    if not task or task.get('status') != 'done':
        return "File not ready", 400
        
    file_path = task.get('file_path')
    filename = task.get('filename')
    
    def remove_file(path, delay=600): # 10 minutes to auto clean
        time.sleep(delay)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
            
    threading.Thread(target=remove_file, args=(file_path,)).start()
    
    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/api/cleanup/<task_id>', methods=['POST', 'DELETE'])
def cleanup(task_id):
    success = downloader.cleanup_task(task_id)
    if success:
        return jsonify({"status": "ok", "message": "File and task cleaned up successfully."})
    else:
        return jsonify({"status": "error", "message": "Task not found."}), 404

@app.route('/api/remove-bg', methods=['POST'])
def remove_background():
    if 'image' not in request.files:
        return jsonify({"error": "Mana fotonya, Bro? Belum di-upload nih."}), 400
    
    try:
        file = request.files['image']
        input_image = Image.open(file.stream)
        
        output_image = remove(input_image, session=session)
        
        img_io = io.BytesIO()
        output_image.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        return jsonify({"error": f"Aduh, ada masalah pas rendering: {str(e)}"}), 500

@app.route('/api/sms-tester', methods=['POST'])
def sms_tester():
    data = request.json
    target = data.get('target')
    count = int(data.get('count', 1))
    
    if not target:
        return jsonify({"error": "Nomor targetnya diisi dulu dong."}), 400

    def send_logic(target_num, loop_count):
        for i in range(loop_count):
            print(f"[{i+1}] Testing sinyal ke {target_num}...")
            time.sleep(1) 

    thread = threading.Thread(target=send_logic, args=(target, count))
    thread.start()

    return jsonify({
        "status": "success",
        "message": f"Siap! Testing buat {target} jalan di background ya."
    })

if __name__ == '__main__':
    # host='0.0.0.0' allows external connections (from Vercel / Public IP)
    app.run(host='0.0.0.0', debug=True, port=5000)
