import yt_dlp
import os
import re
import uuid
import threading
import time
import shutil
from pathlib import Path
from PIL import Image

try:
    import instaloader
    L_INSTA = instaloader.Instaloader()
except ImportError:
    L_INSTA = None

# In-memory store for task progress. In a real app we'd use Redis or a DB.
TASKS = {}
DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- STARTUP CLEANUP ---
# Hapus semua file download sisa dari sesi sebelumnya saat server start
def startup_cleanup():
    try:
        count = 0
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                count += 1
        if count > 0:
            print(f"[YT Startup Cleanup] Dihapus {count} file sisa download.")
    except Exception as e:
        print(f"[YT Startup Cleanup] Error: {e}")

startup_cleanup()

def clean_filename(title, max_length=100):
    cleaned = re.sub(r'[^\w\s-]', '', title)
    return cleaned.strip()[:max_length]

def get_info(url):
    is_threads = 'threads' in url.lower()
    if is_threads:
        match = re.search(r'/post/([^/?#]+)', url)
        if match:
            url = f"https://www.instagram.com/p/{match.group(1)}/"
            
    ydl_opts = {
        'quiet': True,
        'no_warnings': True
    }
    
    cookie_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')
    if os.path.exists(cookie_path) and 'youtube.com' not in url.lower() and 'youtu.be' not in url.lower():
        ydl_opts['cookiefile'] = cookie_path
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            duration = info.get('duration', 0)
            if duration > 3600:
                raise Exception("Video ditolak: Durasi maksimal yang diizinkan untuk semua proses adalah 1 jam.")
            
            # Cukup gunakan daftar bitrate konversi tetap untuk MP3 karena FFmpeg akan memprosesnya.
            audio_formats = [
                {'format_id': 'bestaudio', 'ext': 'mp3', 'abr': 512, 'filesize': 0},
                {'format_id': 'bestaudio', 'ext': 'mp3', 'abr': 320, 'filesize': 0},
                {'format_id': 'bestaudio', 'ext': 'mp3', 'abr': 256, 'filesize': 0},
                {'format_id': 'bestaudio', 'ext': 'mp3', 'abr': 192, 'filesize': 0},
                {'format_id': 'bestaudio', 'ext': 'mp3', 'abr': 150, 'filesize': 0},
            ]
            
            video_formats = []
            for f in info.get('formats', []):
                vcodec = str(f.get('vcodec', 'none')).lower()
                if vcodec != 'none' and 'image' not in vcodec and vcodec not in ['mjpeg', 'png', 'webp']:
                    if f.get('height'):
                        video_formats.append({
                            'format_id': f.get('format_id', 'best'),
                            'ext': f.get('ext', 'mp4'),
                            'resolution': f.get('height'),
                            'vcodec': f.get('vcodec'),
                            'filesize': f.get('filesize') or 0
                        })
    
            unique_videos = {}
            for v in video_formats:
                res = v['resolution']
                if res not in unique_videos or v['filesize'] > unique_videos[res]['filesize']:
                    unique_videos[res] = v
            
            video_formats = sorted(list(unique_videos.values()), key=lambda x: x['resolution'], reverse=True)
    
            image_formats = []
            for f in info.get('formats', []):
                ext = f.get('ext', '')
                vcodec = str(f.get('vcodec', 'none')).lower()
                # Extract image formats
                if ext in ['jpg', 'jpeg', 'png', 'webp'] or 'image' in vcodec or vcodec in ['mjpeg', 'png', 'webp']:
                    res = f.get('height') or f.get('width') or 0
                    url_f = f.get('url')
                    fmt_id = f"url:{url_f}" if url_f else f.get('format_id', 'best')
                    
                    image_formats.append({
                        'format_id': fmt_id,
                        'ext': ext or 'jpg',
                        'resolution': res,
                        'filesize': f.get('filesize') or 0
                    })
                    
            if not image_formats:
                for t in info.get('thumbnails', []):
                    res = t.get('height') or t.get('width') or 0
                    url_t = t.get('url', '')
                    if url_t:
                        image_formats.append({
                            'format_id': f"url:{url_t}",
                            'ext': 'jpg',
                            'resolution': res,
                            'filesize': 0
                        })
    
            unique_images = {}
            for img in image_formats:
                res = img['resolution']
                if res not in unique_images or img['filesize'] > unique_images[res]['filesize']:
                    unique_images[res] = img
            image_formats = sorted(list(unique_images.values()), key=lambda x: x['resolution'], reverse=True)
    
            title_raw = info.get('title', 'Unknown')
            if len(title_raw) > 80:
               title_raw = title_raw[:77] + "..."
            
            extractor = info.get('extractor_key', '').lower()
            
            # Mapping nama social media menjadi singkatan
            mapping = {
                'youtube': 'YT',
                'facebook': 'FB',
                'twitter': 'TW',
                'instagram': 'IG',
                'tiktok': 'TT',
                'threads': 'TH'
            }
            if is_threads:
                prefix = 'TH'
            else:
                prefix = mapping.get(extractor, extractor.upper()[:2]) if extractor else 'MEDIA'
                
            display_title = f"[{prefix}] {title_raw}"
    
            return {
                'title': display_title,
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'formats': {
                    'audio': audio_formats,
                    'video': video_formats,
                    'image': image_formats
                }
            }
    except Exception as e:
        if 'instagram.com' in url.lower() and L_INSTA:
            try:
                match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?#]+)', url)
                if match:
                    shortcode = match.group(1)
                    post = instaloader.Post.from_shortcode(L_INSTA.context, shortcode)
                    image_formats = []
                    
                    if post.typename == 'GraphSidecar':
                        for node in post.get_sidecar_nodes():
                            if not getattr(node, 'is_video', False):
                                image_formats.append({
                                    'format_id': f"url:{node.display_url}",
                                    'ext': 'jpg',
                                    'resolution': getattr(node, 'dimensions', [0,0])[1] if hasattr(node, 'dimensions') else 0,
                                    'filesize': 0
                                })
                    else:
                        if not post.is_video:
                            image_formats.append({
                                'format_id': f"url:{post.url}",
                                'ext': 'jpg',
                                'resolution': 0,
                                'filesize': 0
                            })
                    
                    if image_formats:
                        caption = post.caption if post.caption else "Instagram Photo"
                        if len(caption) > 80:
                            caption = caption[:77] + "..."
                        return {
                            'title': f"[{'TH' if is_threads else 'IG'}] {caption}",
                            'thumbnail': post.url,
                            'duration': 0,
                            'formats': {
                                'audio': [],
                                'video': [],
                                'image': image_formats
                            }
                        }
            except Exception:
                pass
        raise e

class MyLogger(object):
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(msg)

def progress_hook(d, task_id):
    if d['status'] == 'downloading':
        try:
            percent_str = d.get('_percent_str', '0.0%').strip()
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            percent_str = ansi_escape.sub('', percent_str)

            percent = float(percent_str.replace('%', ''))
            TASKS[task_id]['progress'] = percent
            TASKS[task_id]['status'] = 'downloading'
            TASKS[task_id]['eta'] = d.get('eta', 0)
            TASKS[task_id]['speed'] = d.get('_speed_str', 'N/A')
        except Exception:
            pass
    elif d['status'] == 'finished':
        TASKS[task_id]['progress'] = 100
        TASKS[task_id]['status'] = 'processing'

def download_task(url, format_type, quality, task_id):
    TASKS[task_id] = {'status': 'starting', 'progress': 0, 'file_path': None, 'error': None}
    
    is_threads = 'threads' in url.lower()
    if is_threads:
        match = re.search(r'/post/([^/?#]+)', url)
        if match:
            url = f"https://www.instagram.com/p/{match.group(1)}/"
            
    try:
        final_title = "Unknown Download"
        
        try:
            ydl_opts_info = {'quiet': True}
            cookie_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')
            if os.path.exists(cookie_path) and 'youtube.com' not in url.lower() and 'youtu.be' not in url.lower():
                ydl_opts_info['cookiefile'] = cookie_path
                
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                
                title_raw = info.get('title', 'Unknown')
                if len(title_raw) > 80:
                   title_raw = title_raw[:77] + "..."
                   
                extractor = info.get('extractor_key', '').lower()
                mapping = {
                    'youtube': 'YT', 'facebook': 'FB', 'twitter': 'TW',
                    'instagram': 'IG', 'tiktok': 'TT', 'threads': 'TH'
                }
                if is_threads:
                    prefix = 'TH'
                else:
                    prefix = mapping.get(extractor, extractor.upper()[:2]) if extractor else 'MEDIA'
                    
                final_title = f"[{prefix}] {title_raw}"
                
                # Pengecekan limitasi durasi dan resolusi
                duration = info.get('duration', 0)
                if duration > 3600:
                    TASKS[task_id]['status'] = 'error'
                    TASKS[task_id]['error'] = "Ditolak: Durasi video melebihi batas maksimal 1 Jam. Mohon maaf, untuk menjaga kestabilan server, kami membatasi unduhan/konversi maksimal 1 jam untuk semua format."
                    return
                
        except Exception as e:
            if format_type == 'image' and quality and str(quality).startswith('url:'):
                final_title = f"[{'TH' if is_threads else 'IG'}] Photo {task_id[:6]}"
            else:
                raise e
            
        clean_title = clean_filename(final_title)
            
        temp_filename = f"{clean_title}_{task_id}"
        
        # ---- DIRECT URL DOWNLOAD FOR IMAGES ----
        if format_type == 'image' and quality and str(quality).startswith('url:'):
            target_url = quality[4:]
            TASKS[task_id]['status'] = 'downloading'
            TASKS[task_id]['progress'] = 50
            
            import urllib.request
            req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
            out_path = os.path.join(DOWNLOAD_DIR, temp_filename + ".jpg")
            
            with urllib.request.urlopen(req) as response, open(out_path, 'wb') as out_file:
                out_file.write(response.read())

            try:
                im = Image.open(out_path)
                rgb_im = im.convert('RGB')
                rgb_im.save(out_path)
            except Exception as e:
                print(f"Direct URL Image conversion failed: {e}")
                
            TASKS[task_id]['status'] = 'done'
            TASKS[task_id]['file_path'] = out_path
            TASKS[task_id]['filename'] = f"{clean_title}.jpg"
            return
        # ----------------------------------------
        
        temp_path = os.path.join(DOWNLOAD_DIR, temp_filename + ".%(ext)s")
        
        ydl_opts = {
            'outtmpl': temp_path,
            'logger': MyLogger(),
            'progress_hooks': [lambda d: progress_hook(d, task_id)]
        }
        
        cookie_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')
        if os.path.exists(cookie_path) and 'youtube.com' not in url.lower() and 'youtu.be' not in url.lower():
            ydl_opts['cookiefile'] = cookie_path
        
        # Deteksi Universal (Windows / Linux)
        import shutil
        system_ffmpeg = shutil.which('ffmpeg')
        local_ffmpeg = os.path.join(os.getcwd(), 'ffmpeg.exe')
        
        if system_ffmpeg:
            ydl_opts['ffmpeg_location'] = system_ffmpeg
        elif os.path.exists(local_ffmpeg):
            ydl_opts['ffmpeg_location'] = local_ffmpeg

        if format_type == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': str(quality) if quality else '320',
            }]
            final_ext = 'mp3'
        elif format_type == 'mp4':
            if str(quality).isdigit():
                ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best / best[height<={quality}] / best'
            else:
                ydl_opts['format'] = f'{quality}+bestaudio/best / {quality} / best'
            
            ydl_opts['merge_output_format'] = 'mp4'
            final_ext = 'mp4'
            
        elif format_type == 'image':
            if quality and quality != 'undefined' and 'thumb' not in quality:
                ydl_opts['format'] = f'{quality}/best[ext=jpg]/best[ext=webp]/best'
            else:
                # If it's a thumbnail fallback, we might just try best
                ydl_opts['format'] = 'best[ext=jpg]/best[ext=webp]/best'
            final_ext = 'jpg'
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        out_path = None
        downloaded_ext = None
        for file in os.listdir(DOWNLOAD_DIR):
            # Check temp_filename without extension to catch any resulting file
            if file.startswith(temp_filename):
                out_path = os.path.join(DOWNLOAD_DIR, file)
                downloaded_ext = file.split('.')[-1]
                break
                
        if out_path and os.path.exists(out_path):
            if os.path.getsize(out_path) > 0:
                if format_type == 'image' and downloaded_ext and downloaded_ext.lower() != 'jpg':
                    try:
                        im = Image.open(out_path)
                        rgb_im = im.convert('RGB')
                        new_out_path = os.path.join(DOWNLOAD_DIR, f"{temp_filename}.jpg")
                        rgb_im.save(new_out_path)
                        os.remove(out_path)
                        out_path = new_out_path
                        final_ext = 'jpg'
                    except Exception as e:
                        print(f"Image compression to JPG failed: {e}")
                        final_ext = downloaded_ext
                elif format_type != 'image':
                    final_ext = downloaded_ext

                TASKS[task_id]['status'] = 'done'
                TASKS[task_id]['file_path'] = out_path
                TASKS[task_id]['filename'] = f"{clean_title}.{final_ext}"
                TASKS[task_id]['completed_at'] = time.time()
            else:
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                TASKS[task_id]['status'] = 'error'
                TASKS[task_id]['error'] = "File not found or file is empty after processing."
                TASKS[task_id]['completed_at'] = time.time()
        else:
            TASKS[task_id]['status'] = 'error'
            TASKS[task_id]['error'] = "File not found after processing."
            TASKS[task_id]['completed_at'] = time.time()
            
    except Exception as e:
        TASKS[task_id]['status'] = 'error'
        TASKS[task_id]['error'] = str(e)
        TASKS[task_id]['completed_at'] = time.time()


def start_download(url, format_type, quality=None):
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {'status': 'pending', 'progress': 0}
    t = threading.Thread(target=download_task, args=(url, format_type, quality, task_id))
    t.start()
    return task_id

def get_task_status(task_id):
    return TASKS.get(task_id, None)

def cleanup_task(task_id):
    task = TASKS.get(task_id)
    if not task:
        return False
        
    file_path = task.get('file_path')
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"[+] Berhasil menghapus file dari disk: {file_path}")
        except Exception as e:
            print(f"[-] Gagal menghapus file {file_path}: {e}")
            
    # Hapus jejak dari TASKS dict
    TASKS.pop(task_id, None)
    return True

# --- PERIODIC CLEANUP ---
# Auto hapus file dan state task yang sudah selesai/error lebih dari 10 menit
def periodic_cleanup():
    while True:
        time.sleep(60)
        now = time.time()
        expired_tasks = []
        
        # Scan task
        for tid, tdata in list(TASKS.items()):
            if tdata.get('status') in ['done', 'error']:
                completed_at = tdata.get('completed_at', 0)
                if completed_at and (now - completed_at > 600):  # 10 menit
                    expired_tasks.append(tid)
                    
        # Eksekusi penghapusan
        for tid in expired_tasks:
            task = TASKS.get(tid)
            if task:
                file_path = task.get('file_path')
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"[YT Periodic Cleanup] File kedaluwarsa dihapus: {os.path.basename(file_path)}")
                    except Exception:
                        pass
                TASKS.pop(tid, None)

threading.Thread(target=periodic_cleanup, daemon=True).start()
