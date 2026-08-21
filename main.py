import os
import time
import uuid
import subprocess
import random
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
import yt_dlp
import re
import gc

app = FastAPI(title="Opus Clip Clone API - Full Integration")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pastikan direktori penampung sementara dan klip statis tersedia
os.makedirs("temp", exist_ok=True)
os.makedirs("static/clips", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key.strip()) if api_key else None

jobs_db = {}

class ClipRequest(BaseModel):
    url: str
    aspect_ratio: str = "9:16"
    max_duration: int = 60

def download_youtube_video(job_id: str, url: str, output_path: str):
    # Mendukung PROXY_LIST (dipisah koma) atau PROXY_URL tunggal
    proxy_env = os.getenv("PROXY_LIST") or os.getenv("PROXY_URL")
    
    ydl_opts = {
        'format': 'worst[ext=mp4]/worst/bestvideo[height<=360]+bestaudio/best', 
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'retries': 5,
        'nocheckcertificate': True,
        'rm_cachedir': True,
        'extractor_args': {'youtube': ['client=android', 'player_client=android']} 
    }
    
    if proxy_env:
        proxy_list = [p.strip() for p in proxy_env.split(",") if p.strip()]
        selected_proxy = random.choice(proxy_list)
        ydl_opts['proxy'] = selected_proxy
        jobs_db[job_id]["message"] = "Tahap 1: Mengunduh video menggunakan rotasi proxy Dedicated ISP..."
    else:
        jobs_db[job_id]["message"] = "Tahap 1: Mengunduh video ke peladen (Tanpa Proxy)..."
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return True

def process_video_with_gemini(video_path: str, job_id: str):
    if not client:
        raise Exception("GEMINI_API_KEY belum dikonfigurasi.")
    
    uploaded_file = None
    try:
        jobs_db[job_id]["message"] = "Tahap 2: Mengunggah video ke peladen Google Gemini..."
        uploaded_file = client.files.upload(file=video_path)
        
        jobs_db[job_id]["message"] = "Tahap 2: Menunggu Google memproses video (bisa memakan waktu 2-5 menit)..."
        
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(10)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise Exception("Google gagal/menolak memproses video ini.")

        jobs_db[job_id]["message"] = "Tahap 3: Video siap! Gemini sedang memikirkan momen terbaik..."
        prompt = (
            "Analisis video ini dan berikan daftar timestamp dalam format MM:SS - MM:SS "
            "untuk momen-momen paling menarik yang potensial dijadikan klip pendek vertikal."
        )
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=[uploaded_file, prompt]
        )
        return response.text
    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except:
                pass
        gc.collect()

def cut_video_clips(video_path: str, job_id: str, timestamp_matches):
    output_clips = []
    
    def time_to_seconds(time_str):
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])

    job_clip_dir = os.path.join("static", "clips", job_id)
    os.makedirs(job_clip_dir, exist_ok=True)

    for idx, (start_str, end_str) in enumerate(timestamp_matches):
        start_sec = time_to_seconds(start_str)
        end_sec = time_to_seconds(end_str)
        duration = end_sec - start_sec
        
        if duration <= 0:
            duration = 15

        output_filename = f"clip_{idx + 1}.mp4"
        output_filepath = os.path.join(job_clip_dir, output_filename)

        # Perintah FFmpeg untuk memotong dan melakukan auto-crop vertikal 9:16
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_sec),
            '-i', video_path,
            '-t', str(duration),
            '-vf', "crop=ih*9/16:ih",
            '-c:v', 'libx264', '-c:a', 'aac',
            output_filepath
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            output_clips.append({
                "id": idx + 1,
                "start": start_str,
                "end": end_str,
                "url": f"/static/clips/{job_id}/{output_filename}"
            })
        except subprocess.CalledProcessError:
            continue

    return output_clips

def background_video_pipeline(job_id: str, video_url: str):
    video_path = os.path.join("temp", f"{job_id}_video.mp4")
    try:
        jobs_db[job_id]["status"] = "processing"
        
        download_youtube_video(job_id, video_url, video_path)

        ai_analysis = process_video_with_gemini(video_path, job_id)
        jobs_db[job_id]["analysis"] = ai_analysis

        jobs_db[job_id]["message"] = "Tahap Akhir: Memotong video dengan FFmpeg ke rasio 9:16..."
        timestamp_matches = re.findall(r'(\d{2}:\d{2})\s*[-–to]+\s*(\d{2}:\d{2})', ai_analysis)
        
        generated_clips = []
        if timestamp_matches:
            generated_clips = cut_video_clips(video_path, job_id, timestamp_matches)
        
        jobs_db[job_id]["clips"] = generated_clips
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["message"] = "Semua proses selesai dengan sempurna!"
    except Exception as e:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["message"] = f"Error: {str(e)}"
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)
        gc.collect()

@app.get("/")
def read_root():
    return {"status": "Clipper Project Backend Running - Proxy & FFmpeg Active"}

@app.post("/api/v1/generate-clip-url")
def generate_clip_url(payload: ClipRequest, bg_tasks: BackgroundTasks):
    video_url = payload.url
    if not video_url:
        raise HTTPException(status_code=400, detail="URL kosong.")
    
    job_id = uuid.uuid4().hex[:8]
    jobs_db[job_id] = {
        "status": "queued", 
        "message": "Memulai proses...", 
        "clips": [], 
        "analysis": None,
        "aspect_ratio": payload.aspect_ratio,
        "max_duration": payload.max_duration
    }
    bg_tasks.add_task(background_video_pipeline, job_id, video_url)
    return {"status": "success", "job_id": job_id}

@app.get("/api/v1/status/{job_id}")
def get_job_status(job_id: str):
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tidak ditemukan.")
    return job

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)