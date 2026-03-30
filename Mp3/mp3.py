import yt_dlp
import os
import re
from pathlib import Path

def clean_filename(title):
    # Bersihin nama file dari simbol aneh biar FTP & Windows aman tentram
    cleaned = re.sub(r'[^\w\s-]', '', title)
    return cleaned.strip()

def download_mp3():
    print("="*50)
    print("🎵 TOOL'S MP3 DOWNLOADER (512kbps) 🎵")
    print("="*50)
    
    url = input("\n👉 Paste Link YouTube lagu di sini: ")
    download_folder = str(os.path.join(Path.home(), "Downloads"))
    
    # Ambil info lagu dulu buat ngebersihin judulnya
    print("🔍 Sedang ngecek data lagu...")
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            raw_title = info['title']
            clean_title = clean_filename(raw_title)
    except Exception as e:
        print(f"❌ Yah, gagal ambil info lagu Bro: {e}")
        return

    # Siapin path atau jalur penyimpanannya
    final_path = os.path.join(download_folder, f"{clean_title}.%(ext)s")
    
    print(f"✨ Judul Asli: {raw_title}")
    print(f"🧹 Judul Aman: {clean_title}")
    print("🔥 Kualitas  : Super Mentok Kanan (MP3 512kbps)")
    print("\n🎧 Sedang menyedot audio dan meracik MP3...")

    ydl_opts = {
        # Ambil kualitas audio yang paling bagus dari YouTube
        'format': 'bestaudio/best',
        'outtmpl': final_path,
        # Pastikan ffmpeg ada di folder yang sama
        'ffmpeg_location': os.getcwd(), 
        
        # --- JURUS BARU BUAT NEMBUS 403 FORBIDDEN ---
        # Kita nyamar jadi aplikasi Android/iOS biar gak diblokir YouTube
        'extractor_args': {
            'youtube': {'client': ['android', 'ios']}
        },
        # ---------------------------------------------
        
        # Ini dia bumbu rahasianya buat jadi MP3 512kbps
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '512',
        }],
        
        'quiet': False,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("\n" + "="*50)
        print("✅ MANTAP BRO! Lagu udah siap digeber.")
        print(f"📂 Cek folder 'Downloads', cari file '{clean_title}.mp3'.")
        print("="*50)
    except Exception as e:
        print(f"\n❌ Waduh, ada error nih: {e}")
        print("💡 Tips: Pastikan file 'ffmpeg.exe' masih setia di sebelah script ini ya!")

if __name__ == "__main__":
    download_mp3()