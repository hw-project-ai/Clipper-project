import os
import time
import uuid
import subprocess
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from google import genai
import yt_dlp
import re

app = FastAPI(title="Opus Clip Clone API")

# Memastikan API Key bersih dari spasi tersembunyi
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key.strip()) if api_key else None

os.makedirs("temp", exist_ok=True)

# Database sederhana di memori (in-memory) untuk melacak status pekerjaan
# Catatan: Jika server restart, data ini akan hilang. Untuk produksi nanti kita bisa pakai Redis/Database.
jobs_db = {}

def download_youtube_video(url: str, output_path: str):
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
        'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'web']}},
        'http_chunk_size': 10485760,
    }
    if proxy_url:
        ydl_opts['proxy'] = proxy_url.strip()
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return True

def process_video_with_gemini(video_path: str):
    if not client:
        raise Exception("GEMINI_API_KEY belum dikonfigurasi.")
    max_retries = 4
    base_delay = 2

    for attempt in range(max_retries):
        uploaded_file = None
        try:
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
            return result_text
        except Exception as e:
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                except:
                    pass
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                raise Exception(f"Gagal memproses dengan Gemini: {str(e)}")

def crop_video_segment(input_path: str, start_time: str, end_time: str, output_path: str):
    command = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-to", str(end_time),
        "-i", input_path,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        output_path
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Error FFmpeg: {result.stderr}")
        return False
    return True

def background_video_pipeline(job_id: str, video_url: str):
    """
    Fungsi ini berjalan di latar belakang (background) agar tidak memicu Timeout 502.
    """
    video_path = os.path.join("temp", f"{job_id}_video.mp4")
    
    try:
        # Step 1: Download
        jobs_db[job_id]["status"] = "processing"
        jobs_db[job_id]["message"] = "Mengunduh video dari YouTube..."
        download_youtube_video(video_url, video_path)

        # Step 2: AI Analysis
        jobs_db[job_id]["message"] = "Menganalisis momen dengan Gemini AI..."
        ai_analysis = process_video_with_gemini(video_path)
        jobs_db[job_id]["analysis"] = ai_analysis

        # Step 3: Cropping FFmpeg
        jobs_db[job_id]["message"] = "Memotong video menjadi format vertikal..."
        timestamp_matches = re.findall(r'(\d{2}:\d{2})\s*[-–to]+\s*(\d{2}:\d{2})', ai_analysis)
        
        generated_clips = []
        if timestamp_matches:
            for idx, (start, end) in enumerate(timestamp_matches[:3]):
                clip_filename = f"{job_id}_clip_{idx+1}.mp4"
                clip_output_path = os.path.join("temp", clip_filename)
                
                success = crop_video_segment(video_path, start, end, clip_output_path)
                if success:
                    generated_clips.append({
                        "id": idx + 1,
                        "start": start,
                        "end": end,
                        "file": clip_filename
                    })
        
        jobs_db[job_id]["clips"] = generated_clips
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["message"] = "Proses selesai!"

    except Exception as e:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["message"] = str(e)
    finally:
        # Bersihkan file mentah yang berat
        if os.path.exists(video_path):
            os.remove(video_path)

@app.get("/")
def read_root():
    return {"status": "Clipper Project Backend is running smoothly."}

@app.post("/api/v1/generate-clip-url")
def generate_clip_url(payload: dict, bg_tasks: BackgroundTasks):
    video_url = payload.get("url")
    if not video_url:
        raise HTTPException(status_code=400, detail="URL YouTube tidak boleh kosong.")

    # Buat Job ID unik
    job_id = uuid.uuid4().hex[:8]
    
    # Inisialisasi status di database memori
    jobs_db[job_id] = {
        "status": "queued",
        "message": "Pekerjaan dimasukkan ke dalam antrean...",
        "url": video_url,
        "analysis": None,
        "clips": []
    }

    # Lempar proses berat ke background task
    bg_tasks.add_task(background_video_pipeline, job_id, video_url)

    # Langsung kembalikan respons HTTP agar tidak terkena Timeout 502
    return {
        "status": "success",
        "job_id": job_id,
        "message": "Proses dimulai di latar belakang. Silakan cek status menggunakan Job ID ini."
    }

@app.get("/api/v1/status/{job_id}")
def get_job_status(job_id: str):
    """
    Endpoint untuk mengecek sampai mana proses pengerjaan video.
    """
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID tidak ditemukan.")
    return job

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)