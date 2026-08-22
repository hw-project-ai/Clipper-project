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

# --- Modul 3: OpenCV Face Tracking & PURE OPENCV TEXT RENDERING ---

def cut_video_clips_with_tracking(video_path: str, job_id: str, timestamp_matches):
    """Memotong video 9:16 dengan Face Tracking dan OpenCV Karaoke Text (Tanpa ImageMagick)."""
    output_clips = []
    job_clip_dir = os.path.join("static", "clips", job_id)
    os.makedirs(job_clip_dir, exist_ok=True)
    
    cv2_base_path = os.path.dirname(os.path.abspath(cv2.__file__))
    cascade_path = os.path.join(cv2_base_path, 'data', 'haarcascade_frontalface_default.xml')
    
    if not os.path.exists(cascade_path):
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'

    face_cascade = cv2.CascadeClassifier(cascade_path)

    with VideoFileClip(video_path) as video:
        for idx, clip_data in enumerate(timestamp_matches):
            start_sec = clip_data['start']
            end_sec = min(video.duration, clip_data['end'])
            output_filename = f"clip_{idx + 1}.mp4"
            output_filepath = os.path.join(job_clip_dir, output_filename)

            try:
                subclip = video.subclip(start_sec, end_sec)
                w, h = subclip.size
                target_w = int(h * (9 / 16))
                
                last_x_center = w / 2 
                smoothing_factor = 0.1 
                
                def track_and_crop(get_frame, t):
                    nonlocal last_x_center
                    frame = get_frame(t)
                    
                    # 1. Logika Pelacakan Wajah
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    
                    if len(faces) > 0:
                        faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
                        x, y, fw, fh = faces[0]
                        face_center = x + (fw / 2)
                        current_x_center = last_x_center + (face_center - last_x_center) * smoothing_factor
                    else:
                        current_x_center = last_x_center
                        
                    last_x_center = current_x_center
                    
                    x1 = int(max(0, current_x_center - (target_w / 2)))
                    x2 = int(x1 + target_w)
                    
                    if x2 > w:
                        x2 = w
                        x1 = w - target_w
                        
                    # Salin *frame* agar bisa digambari teks oleh OpenCV
                    cropped_frame = frame[:, x1:x2].copy()
                    
                    # 2. Logika Pembuatan Subtitle Murni OpenCV (Mencegah Error ImageMagick)
                    absolute_time = start_sec + t
                    active_word = ""
                    
                    if 'words' in clip_data:
                        for word_info in clip_data['words']:
                            w_start = word_info.get('start', 0)
                            w_end = word_info.get('end', 0)
                            # Jika waktu saat ini berada di antara durasi kata, ambil kata tersebut
                            if w_start <= absolute_time <= w_end:
                                active_word = word_info.get('word', '').strip()
                                break
                    
                    if active_word:
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 1.3
                        thickness = 3
                        
                        # Menghitung ukuran teks agar bisa diletakkan tepat di tengah (Center)
                        text_size = cv2.getTextSize(active_word, font, font_scale, thickness)[0]
                        text_x = (target_w - text_size[0]) // 2
                        text_y = int(h * 0.75) # Posisi teks di 75% ketinggian layar bawah
                        
                        # Lapisan 1: Garis Tepi (Stroke) Tebal Berwarna Hitam
                        cv2.putText(cropped_frame, active_word, (text_x, text_y), font, font_scale, (0, 0, 0), thickness + 4, cv2.LINE_AA)
                        
                        # Lapisan 2: Warna Utama Teks (Kuning Solid - BGR format)
                        cv2.putText(cropped_frame, active_word, (text_x, text_y), font, font_scale, (0, 255, 255), thickness, cv2.LINE_AA)
                        
                    return cropped_frame

                tracked_clip = subclip.fl(track_and_crop)
                
                tracked_clip.write_videofile(
                    output_filepath, 
                    codec="libx264", 
                    audio_codec="aac", 
                    preset="fast",
                    logger=None
                )
                
                start_str = time.strftime('%M:%S', time.gmtime(start_sec))
                end_str = time.strftime('%M:%S', time.gmtime(end_sec))
                
                output_clips.append({
                    "id": idx + 1,
                    "start": start_str,
                    "end": end_str,
                    "url": f"/static/clips/{job_id}/{output_filename}"
                })
                
            except Exception as e:
                print(f"Gagal memotong klip {idx+1}: {e}")
                continue

    return output_clips

# --- Modul Utama: Orchestrator Pipeline ---

def background_video_pipeline(job_id: str, video_url: str):
    video_path = os.path.join("temp", f"{job_id}_video.mp4")
    try:
        jobs_db[job_id]["status"] = "processing"
        
        download_youtube_video(job_id, video_url, video_path)

        ai_analysis_text, timestamp_matches = process_video_with_groq(video_path, job_id)
        jobs_db[job_id]["analysis"] = ai_analysis_text

        jobs_db[job_id]["message"] = "Tahap Akhir: Merender klip dengan Face Tracking & Subtitle AI..."
        
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