import os
import time
import uuid
import subprocess
import uvicorn
from fastapi import FastAPI, HTTPException
from google import genai
import yt_dlp
import re

app = FastAPI(title="Opus Clip Clone API")

# Memastikan API Key bersih dari spasi tersembunyi
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key.strip()) if api_key else None

os.makedirs("temp", exist_ok=True)

def download_youtube_video(url: str, output_path: str):
    """
    Mengunduh video YouTube menggunakan yt-dlp dengan PROXY_URL
    untuk melewati pembatasan bot dan error 403.
    """
    proxy_url = os.getenv("PROXY_URL")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'retries': 15,
        'fragment_retries': 15,
        'nocheckcertificate': True,
        'rm_cachedir': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        },
        'http_chunk_size': 10485760,
    }

    if proxy_url:
        ydl_opts['proxy'] = proxy_url.strip()
        print(f"[Clipper] Menggunakan PROXY_URL untuk mengunduh video...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Gagal mengunduh video: {e}")
        raise HTTPException(status_code=500, detail=f"Gagal mengunduh video data: {str(e)}")

def process_video_with_gemini(video_path: str):
    """
    Mengunggah dan memproses video ke Gemini menggunakan klien baru (google.genai)
    dengan model gemini-3.1-flash-lite serta penanganan error yang tangguh.
    """
    if not client:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY belum dikonfigurasi di server.")

    max_retries = 4
    base_delay = 2

    for attempt in range(max_retries):
        uploaded_file = None
        try:
            print(f"Mengunggah file ke Gemini (Percobaan {attempt + 1}/{max_retries})...")
            
            uploaded_file = client.files.upload(file=video_path)
            
            prompt = (
                "Analisis video ini dan berikan daftar timestamp dalam format MM:SS - MM:SS "
                "untuk momen-momen paling menarik yang potensial dijadikan klip pendek vertikal "
                "beserta judul dan alasannya."
            )
            
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[uploaded_file, prompt]
            )
            result_text = response.text
            
            if uploaded_file:
                client.files.delete(name=uploaded_file.name)
                print("File media dibersihkan dari server Gemini.")
                
            return result_text

        except Exception as e:
            print(f"Kendala pada Gemini (Percobaan {attempt + 1}): {e}")
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
            
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                raise HTTPException(status_code=503, detail=f"Gagal memproses video dengan Gemini API: {str(e)}")

def crop_video_segment(input_path: str, start_time: str, end_time: str, output_path: str):
    """
    Memotong video berdasarkan timestamp dan mengubahnya menjadi format vertikal 9:16 (1080x1920) menggunakan FFmpeg.
    """
    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start_time),
        "-to", str(end_time),
        "-i", input_path,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        output_path
    ]

    try:
        print(f"[Clipper] Memotong video dari {start_time} hingga {end_time}...")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            print(f"Error FFmpeg: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Terjadi kesalahan saat menjalankan FFmpeg: {e}")
        return False

@app.get("/")
def read_root():
    return {"status": "Clipper Project Backend is running smoothly."}

@app.post("/api/v1/generate-clip-url")
def generate_clip_url(payload: dict):
    video_url = payload.get("url")
    if not video_url:
        raise HTTPException(status_code=400, detail="URL YouTube tidak boleh kosong.")

    file_id = uuid.uuid4().hex[:8]
    video_path = os.path.join("temp", f"{file_id}_video.mp4")

    try:
        # 1. Unduh Video
        download_youtube_video(video_url, video_path)

        # 2. Proses Analisis dengan Gemini
        ai_analysis = process_video_with_gemini(video_path)

        # 3. Ekstraksi timestamp otomatis dari teks Gemini (mencari pola MM:SS - MM:SS)
        timestamp_matches = re.findall(r'(\d{2}:\d{2})\s*[-–to]+\s*(\d{2}:\d{2})', ai_analysis)
        
        generated_clips = []
        if timestamp_matches:
            # Ambil hingga 3 klip pertama untuk dipotong secara otomatis sebagai contoh
            for idx, (start, end) in enumerate(timestamp_matches[:3]):
                clip_filename = f"{file_id}_clip_{idx+1}.mp4"
                clip_output_path = os.path.join("temp", clip_filename)
                
                success = crop_video_segment(video_path, start, end, clip_output_path)
                if success:
                    generated_clips.append({
                        "id": idx + 1,
                        "start": start,
                        "end": end,
                        "file": clip_filename
                    })

        # 4. Bersihkan video mentah utama setelah selesai diproses
        if os.path.exists(video_path):
            os.remove(video_path)

        return {
            "status": "success",
            "analysis": ai_analysis,
            "clips": generated_clips
        }

    except HTTPException as he:
        if os.path.exists(video_path):
            os.remove(video_path)
        raise he
    except Exception as e:
        if os.path.exists(video_path):
            os.remove(video_path)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)