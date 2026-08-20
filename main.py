from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # <-- Tambahkan ini
import shutil
import os
import uuid
from services.gemini_analyzer import analyze_and_get_highlights
from services.video_editor import crop_and_cut_video
from config import settings

app = FastAPI(title="Opus Clip Clone - Gemini Edition")

# --- TAMBAHKAN BLOK INI ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mengizinkan akses dari frontend mana pun
    allow_credentials=True,
    allow_methods=["*"],  # Mengizinkan semua method (POST, GET, dll)
    allow_headers=["*"],  # Mengizinkan semua header
)
# --------------------------

@app.post("/api/v1/generate-clip")
async def generate_clip(video: UploadFile = File(...)):
    unique_id = str(uuid.uuid4())[:8]
    temp_video_path = os.path.join(settings.TEMP_DIR, f"{unique_id}_{video.filename}")
    
    try:
        with open(temp_video_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
            
        highlight_data = analyze_and_get_highlights(temp_video_path)
        
        output_name = f"viral_{unique_id}.mp4"
        final_video_path = crop_and_cut_video(
            input_path=temp_video_path,
            start_time=highlight_data['start_time_seconds'],
            end_time=highlight_data['end_time_seconds'],
            output_filename=output_name
        )
        
        return {
            "status": "success",
            "message": "Klip viral berhasil dibuat",
            "data": highlight_data,
            "file_path": final_video_path
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)