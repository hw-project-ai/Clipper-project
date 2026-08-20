import os
import time
import uuid
import subprocess
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from google import genai
import yt_dlp
import re
import gc

app = FastAPI(title="Opus Clip Clone API")

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key.strip()) if api_key else None

os.makedirs("temp", exist_ok=True)
jobs_db = {}

def download_youtube_video(url: str, output_path: str):
    proxy_url = os.getenv("PROXY_URL")
    ydl_opts = {
        'format': 'worst[ext=mp4]/worst',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'retries': 3,
        'nocheckcertificate': True,
        'rm_cachedir': True,
    }
    if proxy_url:
        ydl_opts['proxy'] = proxy_url.strip()
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return True

def process_video_with_gemini(video_path: str):
    if not client:
        raise Exception("GEMINI_API_KEY belum dikonfigurasi.")
    
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=video_path)
        prompt = (
            "Analisis video ini dan berikan daftar timestamp dalam format MM:SS - MM:SS "
            "untuk momen-momen paling menarik yang potensial dijadikan klip pendek vertikal."
        )
        # Menggunakan model gemini-3.1-flash-lite sesuai permintaanmu yang cepat dan ringan
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

def crop_video_segment(input_path: str, start_time: str, end_time: str, output_path: str):
    command = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-to", str(end_time),
        "-i", input_path,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        output_path
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    gc.collect()
    return result.returncode == 0

def background_video_pipeline(job_id: str, video_url: str):
    video_path = os.path.join("temp", f"{job_id}_video.mp4")
    try:
        jobs_db[job_id]["status"] = "processing"
        jobs_db[job_id]["message"] = "Mengunduh video dari YouTube..."
        download_youtube_video(video_url, video_path)

        jobs_db[job_id]["message"] = "Menganalisis momen dengan Gemini 3.1 Flash Lite..."
        ai_analysis = process_video_with_gemini(video_path)
        jobs_db[job_id]["analysis"] = ai_analysis

        if os.path.exists(video_path):
            os.remove(video_path)
        gc.collect()

        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["message"] = "Analisis selesai dengan sukses!"
    except Exception as e:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["message"] = str(e)
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)
        gc.collect()

@app.get("/")
def read_root():
    return {"status": "Clipper Project Backend is running smoothly."}

@app.post("/api/v1/generate-clip-url")
def generate_clip_url(payload: dict, bg_tasks: BackgroundTasks):
    video_url = payload.get("url")
    if not video_url:
        raise HTTPException(status_code=400, detail="URL YouTube tidak boleh kosong.")
    
    job_id = uuid.uuid4().hex[:8]
    jobs_db[job_id] = {"status": "queued", "message": "Pekerjaan dimasukkan ke dalam antrean...", "clips": [], "analysis": None}
    bg_tasks.add_task(background_video_pipeline, job_id, video_url)
    return {"status": "success", "job_id": job_id}

@app.get("/api/v1/status/{job_id}")
def get_job_status(job_id: str):
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID tidak ditemukan.")
    return job

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)