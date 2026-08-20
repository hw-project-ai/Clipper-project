from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import yt_dlp
import os
import uuid
from services.gemini_analyzer import analyze_and_get_highlights
from services.video_editor import crop_and_cut_video
from config import settings

app = FastAPI(title="Opus Clip Clone - Stable Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/files", StaticFiles(directory=settings.OUTPUT_DIR), name="static_files")

class VideoURL(BaseModel):
    url: str
    resolution: Optional[str] = "best" # Defaultnya akan mengambil yang terbaik

@app.post("/api/v1/generate-clip-url")
async def generate_clip_from_url(payload: VideoURL):
    unique_id = str(uuid.uuid4())[:8]
    temp_video_path = os.path.join(settings.TEMP_DIR, f"{unique_id}_video.mp4")
    
    # 1. Menentukan format resolusi secara dinamis berdasarkan permintaanmu
    if payload.resolution and payload.resolution != "best":
        # Jika kau meminta 720, 1080, dsb.
        format_str = f'bestvideo[height<={payload.resolution}][ext=mp4]+bestaudio[ext=m4a]/best[height<={payload.resolution}][ext=mp4]/best'
    else:
        # Jika kau membiarkannya 'best' atau kosong, ambil resolusi tertinggi
        format_str = 'best[ext=mp4]/best'

    # 2. Konfigurasi yt-dlp yang tangguh
    ydl_opts = {
        'format': format_str,
        'outtmpl': temp_video_path,
        'quiet': True,
        'no_warnings': True,
        # INI PENTING: Memaksa yt-dlp mengulang unduhan 15 kali jika proksi Decodo putus (SSL failure)
        'retries': 15,
        'fragment_retries': 15,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        }
    }
    
    if settings.PROXY_URL:
        ydl_opts['proxy'] = settings.PROXY_URL
        print(f"[Clipper] Menggunakan proxy untuk melewati deteksi bot YouTube...")
    
    try:
        # 3. Unduh video menggunakan yt-dlp (akan otomatis me-resume jika putus)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([payload.url])
            
        # 4. Analisis dengan Gemini
        highlight_data = analyze_and_get_highlights(temp_video_path)
        
        # 5. Potong video
        output_name = f"viral_{unique_id}.mp4"
        final_video_path = crop_and_cut_video(
            input_path=temp_video_path,
            start_time=highlight_data['start_time_seconds'],
            end_time=highlight_data['end_time_seconds'],
            output_filename=output_name
        )
        
        return {
            "status": "success",
            "data": highlight_data,
            "download_url": f"/files/{output_name}"
        }
        
    except Exception as e:
        # Mengembalikan pesan error yang lebih bersih
        raise HTTPException(status_code=500, detail=f"ERROR: {str(e)}")