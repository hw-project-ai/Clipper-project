from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uuid
from playwright.async_api import async_playwright
import yt_dlp
from services.gemini_analyzer import analyze_and_get_highlights
from services.video_editor import crop_and_cut_video
from config import settings

app = FastAPI(title="Opus Clip Clone - Playwright Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoURL(BaseModel):
    url: str

async def get_direct_video_stream(youtube_url: str) -> str:
    """Menggunakan Playwright untuk merayapi halaman YouTube secara native dan mendapatkan link video langsung."""
    async with async_playwright() as p:
        # Menjalankan browser Chromium dalam mode headless
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        stream_url = None
        
        # Menangkap request jaringan untuk menemukan file media (.mp4 / m3u8) yang dimuat YouTube
        def handle_request(request):
            nonlocal stream_url
            if ".googlevideo.com/videoplayback" in request.url and "mime=video" in request.url:
                if not stream_url:
                    stream_url = request.url

        page.on("request", handle_request)
        
        try:
            await page.goto(youtube_url, timeout=60000)
            await page.wait_for_timeout(5000) # Tunggu beberapa detik agar pemutar memuat stream
        except Exception:
            pass
            
        await browser.close()
        return stream_url

@app.post("/api/v1/generate-clip-url")
async def generate_clip_from_url(payload: VideoURL):
    unique_id = str(uuid.uuid4())[:8]
    temp_video_path = os.path.join(settings.TEMP_DIR, f"{unique_id}_video.mp4")
    
    try:
        # 1. Dapatkan link stream langsung via Playwright
        direct_url = await get_direct_video_stream(payload.url)
        
        if not direct_url:
            # Fallback ke yt-dlp standar jika penangkapan jaringan gagal
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': temp_video_path,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([payload.url])
        else:
            # Unduh langsung menggunakan curl/requests dari direct_url yang bersih
            import requests
            r = requests.get(direct_url, stream=True)
            with open(temp_video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        
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