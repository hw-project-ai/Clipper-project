import os
import time
import uuid
import uvicorn
from fastapi import FastAPI, HTTPException
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, InternalServerError
import yt_dlp

app = FastAPI(title="Opus Clip Clone API")

# Konfigurasi API Key Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Pastikan direktori temp ada
os.makedirs("temp", exist_ok=True)

def download_youtube_video(url: str, output_path: str):
    """
    Mengunduh video YouTube menggunakan yt-dlp dengan proksi (PROXY_URL)
    untuk melewati pembatasan bot dan error 403.
    """
    proxy_url = os.getenv("PROXY_URL") # Menggunakan PROXY_URL sesuai setelan Render-mu
    
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
        ydl_opts['proxy'] = proxy_url
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
    Mengirim video ke Gemini menggunakan model gemini-3.1-flash-lite 
    dengan mekanisme Exponential Backoff untuk menghindari error 503.
    """
    max_retries = 4
    base_delay = 2

    for attempt in range(max_retries):
        uploaded_file = None
        try:
            print(f"Mengunggah file ke Gemini (Percobaan {attempt + 1}/{max_retries})...")
            uploaded_file = genai.upload_file(path=video_path)
            
            # Menggunakan model gemini-3.1-flash-lite pilihanmu
            model = genai.GenerativeModel('gemini-3.1-flash-lite')
            prompt = "Analisis video ini dan berikan daftar timestamp (waktu mulai dan selesai) untuk momen-momen paling menarik yang potensial dijadikan klip pendek vertikal beserta alasannya."
            
            response = model.generate_content([uploaded_file, prompt])
            result_text = response.text
            
            if uploaded_file:
                genai.delete_file(uploaded_file.name)
                print("File media dibersihkan dari server Gemini.")
                
            return result_text

        except (ResourceExhausted, ServiceUnavailable, InternalServerError) as e:
            print(f"Server Gemini sibuk (Percobaan {attempt + 1}): {e}")
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass
            
            if attempt < max_retries - 1:
                sleep_time = base_delay * (2 ** attempt)
                time.sleep(sleep_time)
            else:
                raise HTTPException(status_code=503, detail=f"Gagal memproses video dengan Gemini API: {str(e)}")
                
        except Exception as e:
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Error internal Gemini: {str(e)}")

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
        # 1. Unduh Video menggunakan yt-dlp & PROXY_URL
        download_youtube_video(video_url, video_path)

        # 2. Proses dengan Gemini (gemini-3.1-flash-lite)
        ai_analysis = process_video_with_gemini(video_path)

        # 3. Bersihkan file lokal setelah selesai
        if os.path.exists(video_path):
            os.remove(video_path)

        return {
            "status": "success",
            "analysis": ai_analysis
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