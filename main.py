import os
import time
import uuid
import random
import uvicorn
import gc
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp
from playwright.sync_api import sync_playwright

# --- Pustaka AI & Pengolahan Video ---
from groq import Groq
from moviepy.video.io.VideoFileClip import VideoFileClip

app = FastAPI(title="Clipper Studio API - Enterprise AI Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp", exist_ok=True)
os.makedirs("static/clips", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

jobs_db = {}

class ClipRequest(BaseModel):
    url: str
    aspect_ratio: str = "9:16"
    max_duration: int = 60

# --- Modul 1: Ingestion & Bypass Keamanan ---

def generate_fresh_cookies(proxy_url: str = None):
    """Menghasilkan session cookies segar untuk bypass keamanan YouTube."""
    cookie_file_path = f"temp/youtube_cookies_{uuid.uuid4().hex[:6]}.txt"
    
    with sync_playwright() as p:
        browser_args = {"headless": True}
        if proxy_url:
            browser_args["proxy"] = {"server": proxy_url}
            
        browser = p.chromium.launch(**browser_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto("https://www.youtube.com", timeout=30000)
            page.wait_for_timeout(5000) 
            
            cookies = context.cookies()
            
            with open(cookie_file_path, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n\n")
                for cookie in cookies:
                    domain = cookie['domain']
                    include_subdomains = "TRUE" if domain.startswith('.') else "FALSE"
                    path = cookie['path']
                    secure = "TRUE" if cookie['secure'] else "FALSE"
                    expires = str(int(cookie['expires'])) if cookie['expires'] > 0 else "0"
                    name = cookie['name']
                    value = cookie['value']
                    f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                    
            return cookie_file_path
        except Exception as e:
            print(f"Gagal generate cookies: {e}")
            return None
        finally:
            browser.close()

def download_youtube_video(job_id: str, url: str, output_path: str, max_retries: int = 3):
    """
    Mengunduh video mentah dengan mekanisme Auto-Retry agresif.
    Jika terdeteksi blokir bot, sistem akan membangkitkan cookie baru secara otomatis.
    """
    proxy_env = os.getenv("PROXY_LIST") or os.getenv("PROXY_URL")
    proxy_list = [p.strip() for p in proxy_env.split(",")] if proxy_env else []

    for attempt in range(max_retries):
        selected_proxy = random.choice(proxy_list) if proxy_list else None
        
        jobs_db[job_id]["message"] = f"Tahap 1: Membangkitkan session cookies (Percobaan Bypass {attempt + 1}/{max_retries})..."
        cookie_file = generate_fresh_cookies(selected_proxy)
        
        ydl_opts = {
            'format': 'worst[ext=mp4]/worst/bestvideo[height<=360]+bestaudio/best', 
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'rm_cachedir': True,
            'extractor_args': {'youtube': ['player_client=android', 'player_skip=web']},
        }
        
        if selected_proxy:
            ydl_opts['proxy'] = selected_proxy
            
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
            
        jobs_db[job_id]["message"] = f"Tahap 2: Mengunduh video mentah (Percobaan {attempt + 1})..."
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"[Worker] Percobaan {attempt + 1} gagal: {error_msg}")
            
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)
                
            if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
                if attempt < max_retries - 1:
                    jobs_db[job_id]["message"] = "Terdeteksi blokir dari YouTube. Membuang identitas lama dan meretas ulang..."
                    time.sleep(3)
                    continue
            
            if attempt == max_retries - 1:
                raise Exception(f"Gagal mengunduh video setelah {max_retries} kali percobaan pembobolan. Error asli: {error_msg}")

    return False

# --- Modul 2: Cloud AI Transcription (Groq) & Scoring ---

def process_video_with_groq(video_path: str, job_id: str):
    """
    Ekstraksi audio lokal, lalu mengirimkannya ke Groq API (Cloud LPU) 
    untuk transkripsi kilat. Mencegah peladen Render mengalami Out of Memory (OOM).
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise Exception("GROQ_API_KEY belum dikonfigurasi di peladen.")
    
    client = Groq(api_key=groq_api_key)
    audio_path = os.path.join("temp", f"{job_id}_audio.mp3")
    
    try:
        jobs_db[job_id]["message"] = "Tahap 3: Mengekstrak audio untuk dikirim ke Cloud AI..."
        with VideoFileClip(video_path) as video:
            audio = video.audio
            audio.write_audiofile(audio_path, codec='libmp3lame', bitrate='64k', logger=None)
            
        jobs_db[job_id]["message"] = "Tahap 4: Groq AI menganalisis transkrip dalam hitungan detik..."
        with open(audio_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_path, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
        
        jobs_db[job_id]["message"] = "Tahap 5: Menyaring momen viral..."
        
        segments = transcription.segments
        
        scored_segments = []
        for seg in segments:
            duration = seg['end'] - seg['start']
            if duration < 5:
                continue
            word_count = len(seg['text'].split())
            density = word_count / duration 
            scored_segments.append({
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text'],
                'score': density,
                'words': seg.get('words', [])
            })
        
        top_segments = sorted(scored_segments, key=lambda x: x['score'], reverse=True)[:3]
        
        analysis_text = ""
        timestamp_matches = []
        for idx, ts in enumerate(top_segments):
            start_fmt = time.strftime('%M:%S', time.gmtime(ts['start']))
            end_fmt = time.strftime('%M:%S', time.gmtime(ts['end'] + 15)) 
            analysis_text += f"{start_fmt} - {end_fmt}\n{ts['text']}\n\n"
            timestamp_matches.append({
                'start': ts['start'], 
                'end': ts['start'] + 15,
                'words': ts['words'] 
            })
            
        return analysis_text, timestamp_matches

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

# --- Modul 3: OpenCV Face Tracking & MoviePy Rendering ---

def get_face_center(frame, cascade_path):
    """Mendeteksi wajah menggunakan OpenCV."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cascade_path)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    
    if len(faces) > 0:
        faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
        x, y, w, h = faces[0]
        return x + (w / 2)
    return None

# --- Modul 3: Rendering Karaoke Subtitle (Fix Method: subclip) ---
def cut_video_clips_with_tracking(video_path: str, job_id: str, timestamp_matches):
    output_clips = []
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    video = VideoFileClip(video_path)
    
    for idx, clip_data in enumerate(timestamp_matches):
        # MENGGUNAKAN subclip() BUKAN subclipped()
        subclip = video.subclip(clip_data['start'], min(video.duration, clip_data['end']))
        w, h = subclip.size
        target_w = int(h * (9 / 16))
        
        subtitle_clips = []
        for word_obj in clip_data['words']:
            start = word_obj['start'] - clip_data['start']
            duration = word_obj['end'] - word_obj['start']
            txt = TextClip(word_obj['word'], fontsize=70, color='yellow', font='Arial-Bold', stroke_color='black', stroke_width=2)
            txt = txt.set_start(start).set_duration(duration).set_position(('center', 'center'))
            subtitle_clips.append(txt)
            
        last_x = w / 2
        def process_frame(frame):
            nonlocal last_x
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cv2.CascadeClassifier(cascade_path).detectMultiScale(gray, 1.1, 5)
            x_center = faces[0][0] + faces[0][2]/2 if len(faces) > 0 else last_x
            last_x = last_x + (x_center - last_x) * 0.1
            x1 = int(max(0, min(last_x - target_w/2, w - target_w)))
            return frame[:, x1:x1+target_w]

        tracked_clip = subclip.fl_image(process_frame)
        final_clip = CompositeVideoClip([tracked_clip] + subtitle_clips)
        
        output_path = f"static/clips/{job_id}/clip_{idx+1}.mp4"
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        output_clips.append({"id": idx+1, "url": f"/static/clips/{job_id}/clip_{idx+1}.mp4"})
    
    video.close()
    return output_clips

# --- Modul Utama: Orchestrator Pipeline ---

def background_video_pipeline(job_id: str, video_url: str):
    video_path = os.path.join("temp", f"{job_id}_video.mp4")
    try:
        jobs_db[job_id]["status"] = "processing"
        
        download_youtube_video(job_id, video_url, video_path)

        ai_analysis_text, timestamp_matches = process_video_with_groq(video_path, job_id)
        jobs_db[job_id]["analysis"] = ai_analysis_text

        jobs_db[job_id]["message"] = "Tahap Akhir: Merender klip dengan Face Tracking..."
        
        generated_clips = []
        if timestamp_matches:
            generated_clips = cut_video_clips_with_tracking(video_path, job_id, timestamp_matches)
        
        jobs_db[job_id]["clips"] = generated_clips
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["message"] = "Semua proses selesai dengan sempurna!"
        
    except Exception as e:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["message"] = f"Error Server: {str(e)}"
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)
        gc.collect()

@app.post("/api/v1/generate-clip-url")
def generate_clip_url(payload: ClipRequest, bg_tasks: BackgroundTasks):
    video_url = payload.url
    if not video_url:
        raise HTTPException(status_code=400, detail="URL kosong.")
    
    job_id = uuid.uuid4().hex[:8]
    jobs_db[job_id] = {
        "status": "queued", 
        "message": "Memulai proses antrean AI...", 
        "clips": [], 
        "analysis": None
    }
    
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