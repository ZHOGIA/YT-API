# 🚀 Tool's Studio - YouTube Downloader

Phoebe's Studio adalah sebuah Web Application modern dan elegan untuk mengunduh video dan audio dari YouTube (serta berbagai platform lainnya yang didukung oleh `yt-dlp`). Dibuat menggunakan paduan kekuatan **Python (Flask)** sebagai mesin pemroses utama (Backend) dan UI interaktif berdesain *Glassmorphism* (Frontend).

## ✨ Fitur Utama
- **Kualitas Maksimal**: Unduh video MP4 mulai dari resolusi standar (420p) hingga ultra tajam (**4K**).
- **Audio Jernih**: Unduh MP3 dengan bitrate dari yang terendah hingga highest quality (**320kbps**).
- **UI Premium**: Tampilan gelap (Dark Mode) modern dengan efek kaca animasi yang responsif.
- **Asynchronous & Realtime**: Proses ekstraksi dan pengunduhan ditampilkan 100% *real-time* via *Progress Bar* menggunakan arsitektur pemanggilan API modern (tanpa halaman *reload*).
- **Auto-Cleanup**: Menghapus file lokal (*temporary file*) di dalam folder secara otomatis setelah berhasil diunduh.
- **Support Decoupled Architecture**: Mendukung arsitektur terpisah (misalnya hosting Tampilan di Vercel, dan Algoritma diproses di server VPS Linux Anda).

---

## 🛠️ Persyaratan Sistem (Prerequisites)

Sebelum menjalankan aplikasi ini, pastikan komputer/server Anda telah meng-install:
1. **Python 3.8+** (Disarankan Python 3.10 atau versi terbaru)
2. **FFmpeg** 
   - **Windows**: File `ffmpeg.exe` bisa ditaruh satu direktori (folder yang sama) dengan file `app.py`.
   - **Linux (Debian/Ubuntu)**: Harus menginstall program ffmpeg secara global (misal melalui *apt*).

---

## 💻 Cara Install & Menjalankan di Local Windows

1. **Buka folder project di Terminal (Command Prompt / PowerShell)**
   ```powershell
   cd "D:\path\ke\folder\Website downloader YT"
   ```

2. **Buat Virtual Environment (Sangat direkomendasikan)**
   ```powershell
   python -m venv venv
   ```

3. **Aktifkan Virtual Environment**
   ```powershell
   .\venv\Scripts\activate
   ```

4. **Install Dependensi Library / Modules**
   ```powershell
   pip install flask yt-dlp flask-cors
   ```

5. **Jalankan Aplikasi Web-nya!**
   ```powershell
   python app.py
   ```
6. Buka Web Browser Anda (Chrome, Edge, Safari) dan akses link berikut: **`http://127.0.0.1:5000`**

---

## 🐧 Cara Deploy di Server Linux (Debian / Ubuntu)

Sangat cocok jika Anda merencanakan mesin backend untuk stand-by 24/7 di server cloud (VPS).

1. **Update package dan Install FFmpeg serta Python**
   ```bash
   sudo apt update
   sudo apt install ffmpeg python3 python3-venv python3-pip
   ```
2. **Upload folder source-code ini ke server Linux Anda.**
3. **Posisikan terminal di dalam folder kode tersebut.**
4. **Setup Environment & Install Requirements**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install flask yt-dlp flask-cors
   ```
5. **Menjalankan Server (Production Ready)**
   Untuk sekadar test, Anda bisa memanggil `python3 app.py`. Namun, jika ingin berjalan secara daemon/background permanen, sangat disarankan menggunakan **Gunicorn**:
   ```bash
   pip install gunicorn
   gunicorn --bind 0.0.0.0:5000 app:app
   ```
6. (Opsional) Setup Reverse Proxy NGINX agar port 5000 Anda bisa diakses secara publik menggunakan domain Anda.

---

## 🌐 Arsitektur Frontend-Backend Terpisah (Vercel + VPS)

Project ini sangat bisa mendukung setup **Decoupled**. Artinya: FrontEnd (Tampilan Web) menumpang hosting gratis seperti *Vercel/Render*, sedangkan proses download membebani RAM VPS / PC rumah (*Backend*).

**Cara Setting:**
1. File UI saja (`index.html`, `style.css`, `script.js`) di-upload/deploy ke Vercel atau GitHub Pages.
2. File Backend Server Python (`app.py`, `downloader.py`) saja dinaikkan ke server Debian Anda yang siap melayani 24/7.
3. Edit file **`script.js`** yang ada di Vercel: Ubah baris `fetch('/api/...` menjadi alamat Public IP atau Domain VPS yang menyalakan Flask tersebut, contoh:
   ```javascript
   // Sebelumnya:
   fetch('/api/process', ...)

   // Diubah menjadi:
   fetch('http://IP_VPS_ANDA:5000/api/process', ...)
   ```
*Catatan: Hal ini diizinkan karena `app.py` sudah diatur dengan `CORS(app)`.*


