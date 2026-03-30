from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import downloader
import os
import threading
import time

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

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

if __name__ == '__main__':
    # host='0.0.0.0' allows external connections (from Vercel / Public IP)
    app.run(host='0.0.0.0', debug=True, port=5000)
