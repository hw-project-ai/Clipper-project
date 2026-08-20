from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
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

@app.post("/api/v1/generate-clip-url")
async def generate_clip_from_url(payload: VideoURL):
    unique_id = str(uuid.uuid4())[:8]
    temp_video_path = os.path.join(settings.TEMP_DIR, f"{unique_id}_video.mp4")
    
    # Konfigurasi yt-dlp yang dioptimalkan untuk melewati proteksi bot YouTube di server cloud
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': temp_video_path,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        }
    }
    
    # Jika kau nanti ingin memasukkan file cookies.txt di root folder project:
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    
    try:
        # 1. Unduh video menggunakan yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([payload.url])
            
        # 2. Analisis dengan Gemini
        highlight_data = analyze_and_get_highlights(temp_video_path)
        
        # 3. Potong video
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
        raise HTTPException(status_code=500, detail=str(e))