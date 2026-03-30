import yt_dlp
import os
import subprocess
import re
from pathlib import Path

def clean_filename(title):
    # Hapus semua karakter aneh biar FTP & Windows gak error
    # Cuma bolehin Huruf, Angka, Spasi, Strip, dan Underscore
    cleaned = re.sub(r'[^\w\s-]', '', title)
    return cleaned.strip()

def download_and_convert():
    print("="*50)
    print("🛠️  TOOL'S FINAL FIXER (SAFE MODE)  🛠️")
    print("="*50)
    
    url = input("\n👉 Paste Link YouTube: ")
    download_folder = str(os.path.join(Path.home(), "Downloads"))
    
    # Ambil Info Video Dulu buat dapet Judul
    print("🔍 Sedang ngecek judul video...")
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        raw_title = info['title']
        clean_title = clean_filename(raw_title)
    
    print(f"✨ Judul Asli: {raw_title}")
    print(f"🧹 Judul Aman: {clean_title} (Siap buat FTP!)")

    # Nama file mentah & file jadi
    temp_filename = f"{clean_title}_TEMP.mp4"
    final_filename = f"{clean_title}_PremiereReady.mp4"
    
    temp_path = os.path.join(download_folder, temp_filename)
    final_path = os.path.join(download_folder, final_filename)

    # 1. DOWNLOAD (Tanpa convert macem-macem biar gak corrupt)
    print("\n⬇️  Lagi download file mentah (High Res)...")
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': temp_path,
        'quiet': False,
        'ffmpeg_location': os.getcwd(), # Pastikan ffmpeg ada di sini
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"❌ Gagal Download: {e}")
        return

    # 2. CONVERT MANUAL (Lebih stabil buat Premiere)
    print("\n⚙️  Sedang Convert ke format Editor (H.264)...")
    print("☕ Sabar ya, proses ini butuh power CPU...")

    # Perintah FFmpeg manual (Paling Ampuh)
    # -c:v libx264 : Video codec wajib buat Premiere
    # -pix_fmt yuv420p : Format warna wajib buat Premiere
    # -c:a aac : Audio codec standar
    cmd = [
        'ffmpeg', '-i', temp_path,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '22',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-pix_fmt', 'yuv420p', 
        '-y', # Overwrite kalau ada
        final_path
    ]

    try:
        subprocess.run(cmd, check=True)
        print("\n✅ CONVERT SELESAI!")
        
        # Hapus file mentah biar gak menuhin storage
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print("🗑️  File mentah dihapus, sisa file jadi aja.")
            
        print("="*50)
        print(f"📂 File siap pakai: {final_filename}")
        print("🚀 Coba transfer ke HP atau buka di Premiere sekarang!")
        print("="*50)
        
    except subprocess.CalledProcessError:
        print("❌ Gagal Convert! Cek apakah ffmpeg.exe ada di folder script?")
    except Exception as e:
        print(f"❌ Error lain: {e}")

if __name__ == "__main__":
    download_and_convert()