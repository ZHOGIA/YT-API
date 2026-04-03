from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import io
import gc
import uuid
import ctypes
import platform
import requests as http_requests
from PIL import Image
from rembg import remove, new_session
import onnxruntime as ort
import downloader
import os
import threading
import time
import logging

class QuietLogFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # Menyembunyikan log spam dari request root (GET/POST /)
        if 'POST / HTTP' in msg or 'GET / HTTP' in msg:
            return False
        return True

log = logging.getLogger('werkzeug')
log.addFilter(QuietLogFilter())

app = Flask(__name__)
CORS(app)

# --- FORCE OS MEMORY RELEASE ---
# gc.collect() membebaskan Python objects, TAPI glibc (Linux) menyimpan halaman
# bebas di free-list dan tidak mengembalikannya ke OS secara otomatis.
# malloc_trim(0) memaksa glibc mengembalikan semua halaman bebas ke OS sekarang.
def force_os_memory_release():
    try:
        if platform.system() == 'Linux':
            ctypes.CDLL('libc.so.6').malloc_trim(0)
            print("[Memory] malloc_trim: halaman bebas dikembalikan ke OS.")
    except Exception as e:
        print(f"[Memory] malloc_trim gagal (mungkin bukan Linux): {e}")

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

def load_session(model_name, providers):
    try:
        s = new_session(model_name, providers=providers)
        print(f"[+] Model '{model_name}' berhasil dimuat.")
        return s
    except Exception as e:
        print(f"[X] Gagal load '{model_name}' dengan hardware spesifik: {e}. Fallback ke CPU.")
        return new_session(model_name)

# ==========================================================
# KONFIGURASI MODE: remove.bg API vs Local AI
# ==========================================================
# Jika REMOVEBG_API_KEY di-set di environment, gunakan remove.bg API:
#   - Zero RAM untuk AI (tidak ada model ONNX yang dimuat)
#   - Kualitas terbaik (remove.bg adalah gold standard)
#   - Free: 50 gambar/bulan | Berbayar: ~$0.20/gambar
#
# Cara set API key:
#   Linux/Mac : export REMOVEBG_API_KEY="your_key_here"
#   Windows   : setx REMOVEBG_API_KEY "your_key_here"
#   Atau buat file .env lalu jalankan: set -a && source .env && set +a
# ==========================================================
REMOVEBG_API_KEY = os.environ.get('REMOVEBG_API_KEY', '').strip()
USE_REMOVEBG_API  = bool(REMOVEBG_API_KEY)

if USE_REMOVEBG_API:
    print(f"[+] Mode: remove.bg API aktif — tidak ada model AI lokal yang dimuat. Hemat RAM!")
    best_providers = None
    sessions       = {}
    _sessions_lock = threading.Lock()
else:
    print("[*] Mode: Local AI — model akan dimuat saat pertama kali digunakan.")
    best_providers = get_best_provider()

    MODEL_MAP = {
        "human":   "u2net_human_seg",   # Foto manusia / portrait — ringan & fit di 2GB VRAM
        "anime":   "isnet-anime",        # Gambar anime / ilustrasi
        "general": "isnet-general-use",  # Objek umum / produk / hewan
    }
    sessions       = {}
    _sessions_lock = threading.Lock()

    def get_session(model_type):
        """Ambil session model. Load otomatis jika belum pernah dipakai."""
        model_name = MODEL_MAP.get(model_type, MODEL_MAP["human"])
        with _sessions_lock:
            if model_type not in sessions:
                print(f"[Lazy Load] Memuat model '{model_name}' untuk pertama kali...")
                sessions[model_type] = load_session(model_name, best_providers)
                print(f"[Lazy Load] Model '{model_name}' siap digunakan.")
            return sessions[model_type]


# --- TEMP STORAGE UNTUK HASIL REMOVE BG ---
# File disimpan di disk agar RAM langsung bebas setelah proses selesai
# Auto-hapus otomatis setelah 10 menit
BG_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "bg_output")
os.makedirs(BG_OUTPUT_DIR, exist_ok=True)
BG_TASKS = {}          # {file_id: {"path": ..., "created_at": float}}
_bg_lock = threading.Lock()

def startup_cleanup():
    """
    Dijalankan sekali saat app.py start/restart.
    Menangani kasus server crash dimana BG_TASKS (in-memory) hilang
    tapi file di bg_output/ masih tersisa (orphaned files).

    Strategi:
    - File umur > 10 menit  → hapus langsung (sudah kedaluwarsa)
    - File umur < 10 menit  → re-register ke BG_TASKS pakai mtime asli file
                              agar cleanup thread tetap hapus tepat waktu
    """
    now = time.time()
    deleted = 0
    reregistered = 0

    try:
        files = os.listdir(BG_OUTPUT_DIR)
    except Exception:
        return

    for filename in files:
        if not filename.endswith('.png'):
            continue
        file_id   = filename.replace('.png', '')
        file_path = os.path.join(BG_OUTPUT_DIR, filename)
        try:
            file_mtime = os.path.getmtime(file_path)
            age        = now - file_mtime

            if age > 600:  # > 10 menit — kedaluwarsa, hapus sekarang
                os.remove(file_path)
                deleted += 1
                print(f"[Startup Cleanup] Hapus file lama: {filename} (umur: {age:.0f}s)")
            else:          # masih dalam 10 menit — re-register agar thread cleanup tangani
                with _bg_lock:
                    BG_TASKS[file_id] = {
                        "path":       file_path,
                        "created_at": file_mtime   # pakai waktu asli file, bukan sekarang
                    }
                reregistered += 1
                sisa = 600 - age
                print(f"[Startup Cleanup] Re-register: {filename} (akan dihapus dalam {sisa:.0f}s)")
        except Exception as e:
            print(f"[Startup Cleanup] Error saat proses {filename}: {e}")

    if deleted > 0 or reregistered > 0:
        print(f"[Startup Cleanup] Selesai: {deleted} file dihapus, {reregistered} file di-register ulang.")
    else:
        print("[Startup Cleanup] bg_output bersih, tidak ada file lama.")

startup_cleanup()  # Jalankan langsung saat startup

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
    
    if not file_path or not os.path.exists(file_path):
        return "File not found or has been removed from server.", 404
    
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

    file = request.files['image']
    model_type = request.form.get("model_type", "human")

    try:
        # ── MODE 1: remove.bg API ─────────────────────────────────────
        if USE_REMOVEBG_API:
            print(f"[Remove BG] Menggunakan remove.bg API (model_type '{model_type}' diabaikan)")
            response = http_requests.post(
                'https://api.remove.bg/v1.0/removebg',
                files={'image_file': (file.filename, file.stream, file.mimetype)},
                data={'size': 'auto'},
                headers={'X-Api-Key': REMOVEBG_API_KEY},
                timeout=60
            )

            if response.status_code == 200:
                result_bytes = response.content
            elif response.status_code == 402:
                return jsonify({"error": "Kredit remove.bg habis! Tambah kredit di remove.bg atau ganti ke mode lokal."}), 402
            elif response.status_code == 403:
                return jsonify({"error": "API Key remove.bg tidak valid. Periksa konfigurasi REMOVEBG_API_KEY."}), 403
            else:
                try:
                    err_msg = response.json()['errors'][0]['title']
                except Exception:
                    err_msg = f"HTTP {response.status_code}"
                return jsonify({"error": f"remove.bg API error: {err_msg}"}), 500

            # Simpan hasil ke disk
            file_id  = str(uuid.uuid4())
            file_path = os.path.join(BG_OUTPUT_DIR, f"{file_id}.png")
            with open(file_path, 'wb') as f:
                f.write(result_bytes)

            print(f"[Remove BG API] Selesai. File disimpan: {file_id}.png")

        # ── MODE 2: Local AI ──────────────────────────────────────────
        else:
            input_image  = None
            output_image = None
            try:
                input_image = Image.open(file.stream).convert("RGBA")
                selected_session = get_session(model_type)
                print(f"[Remove BG] Menggunakan model lokal: '{model_type}'")

                if model_type == "human":
                    output_image = remove(
                        input_image,
                        session=selected_session,
                        post_process_mask=True,
                        alpha_matting=True,
                        alpha_matting_erode_size=15,
                        alpha_matting_foreground_threshold=240,
                        alpha_matting_background_threshold=20,
                    )
                else:
                    output_image = remove(
                        input_image,
                        session=selected_session,
                        post_process_mask=True,
                        alpha_matting=False
                    )

                del input_image
                input_image = None

                file_id   = str(uuid.uuid4())
                file_path = os.path.join(BG_OUTPUT_DIR, f"{file_id}.png")
                output_image.save(file_path, "PNG")

                del output_image
                output_image = None
                gc.collect()
                force_os_memory_release()
                print(f"[Remove BG] Selesai. File disimpan: {file_id}.png | RAM dibersihkan.")

            finally:
                if input_image  is not None: del input_image
                if output_image is not None: del output_image
                gc.collect()
                force_os_memory_release()

        # Daftarkan untuk auto-hapus 10 menit (berlaku untuk kedua mode)
        with _bg_lock:
            BG_TASKS[file_id] = {"path": file_path, "created_at": time.time()}

        return jsonify({"file_id": file_id})

    except Exception as e:
        return jsonify({"error": f"Aduh, ada masalah pas rendering: {str(e)}"}), 500


@app.route('/api/bg-result/<file_id>', methods=['GET', 'HEAD'])
def bg_result(file_id):
    """Endpoint untuk preview gambar hasil remove-bg."""
    with _bg_lock:
        task = BG_TASKS.get(file_id)
    if not task or not os.path.exists(task.get("path", "")):
        return jsonify({"error": "File tidak ditemukan atau sudah kedaluwarsa (10 menit)."}), 404
    return send_file(task["path"], mimetype='image/png')

@app.route('/api/bg-download/<file_id>', methods=['GET'])
def bg_download(file_id):
    """Endpoint untuk download gambar hasil remove-bg sebagai attachment."""
    with _bg_lock:
        task = BG_TASKS.get(file_id)
    if not task or not os.path.exists(task.get("path", "")):
        return jsonify({"error": "File tidak ditemukan atau sudah kedaluwarsa (10 menit)."}), 404
    return send_file(task["path"], as_attachment=True, download_name="removed-bg.png")


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

def periodic_cleanup():
    while True:
        try:
            now = time.time()
            for filename in os.listdir(downloader.DOWNLOAD_DIR):
                file_path = os.path.join(downloader.DOWNLOAD_DIR, filename)
                if os.path.isfile(file_path):
                    # Check if file is older than 24 hours (86400 seconds)
                    if os.stat(file_path).st_mtime < now - 86400:
                        try:
                            os.remove(file_path)
                            print(f"[Periodic Cleanup] Removed old file: {filename}")
                        except Exception as e:
                            print(f"[Periodic Cleanup] Failed to remove {filename}: {e}")
            
            # Also clean up old TASKS in memory
            stale_task_ids = []
            for task_id, task_data in list(downloader.TASKS.items()):
                # If it's been done or err for a long time, we might want to pop it...
                # But since TASKS doesn't store timestamps, we just let it be or pop tasks that have no file left.
                fpath = task_data.get("file_path")
                if task_data.get("status") in ["done", "error"]:
                    if fpath and not os.path.exists(fpath):
                        stale_task_ids.append(task_id)
            
            for tid in stale_task_ids:
                downloader.TASKS.pop(tid, None)
                print(f"[Periodic Cleanup] Cleared stale task: {tid}")

        except Exception as e:
            print(f"[Periodic Cleanup Error]: {e}")
            
        time.sleep(3600)  # Sleep for 1 hour before checking again

# Start background cleanup thread (YouTube downloads — 24 jam)
threading.Thread(target=periodic_cleanup, daemon=True).start()

# --- AUTO HAPUS HASIL REMOVE BG SETELAH 10 MENIT ---
def bg_cleanup():
    while True:
        time.sleep(60)  # cek setiap 60 detik
        now = time.time()
        expired_ids = []
        with _bg_lock:
            for fid, data in list(BG_TASKS.items()):
                if now - data["created_at"] > 600:  # 10 menit = 600 detik
                    expired_ids.append((fid, data["path"]))
        for fid, path in expired_ids:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"[BG Cleanup] File kedaluwarsa dihapus: {fid}.png")
            except Exception as e:
                print(f"[BG Cleanup] Gagal hapus {fid}: {e}")
            with _bg_lock:
                BG_TASKS.pop(fid, None)

threading.Thread(target=bg_cleanup, daemon=True).start()

# --- PERIODIC MEMORY GC ---
# Setiap 10 menit, paksa Python bebaskan semua object yang sudah tidak dipakai
# Ini penting karena rembg/onnxruntime/PIL bisa menahan buffer besar di RAM
def periodic_memory_gc():
    while True:
        time.sleep(600)  # 10 menit
        collected = gc.collect()
        force_os_memory_release()  # Paksa kembalikan halaman ke OS
        print(f"[Memory GC] Periodic cleanup selesai — {collected} objek dibebaskan.")


threading.Thread(target=periodic_memory_gc, daemon=True).start()

if __name__ == '__main__':
    # host='0.0.0.0' allows external connections (from Vercel / Public IP)
    app.run(host='0.0.0.0', debug=True, port=5000)
