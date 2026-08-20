import os
import time
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, InternalServerError

app = FastAPI(title="Opus Clip Clone API")

# Konfigurasi API Key Gemini
# Pastikan GEMINI_API_KEY sudah diset di environment variable Render
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def process_video_with_gemini(video_path: str):
    """
    Mengirim video ke Gemini dengan mekanisme Exponential Backoff 
    untuk menghindari error 503 Service Unavailable / High Demand.
    Menggunakan gemini-1.5-flash agar lebih stabil dan cepat.
    """
    max_retries = 4
    base_delay = 2  # Jeda awal 2 detik

    for attempt in range(max_retries):
        uploaded_file = None
        try:
            print(f"Mencoba mengunggah dan memproses video dengan Gemini (Percobaan {attempt + 1}/{max_retries})...")
            
            # Mengunggah file video ke server Gemini
            uploaded_file = genai.upload_file(path=video_path)
            
            # Menggunakan model flash untuk ketahanan terhadap beban tinggi
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Prompt untuk analisis highlight video
            prompt = "Analisis video ini dan berikan poin-poin momen paling menarik atau penting untuk dijadikan klip pendek vertikal."
            response = model.generate_content([uploaded_file, prompt])
            
            result_text = response.text
            
            # Bersihkan file dari server Gemini setelah selesai
            if uploaded_file:
                genai.delete_file(uploaded_file.name)
                print("File media berhasil dihapus dari server Gemini.")
                
            return result_text

        except (ResourceExhausted, ServiceUnavailable, InternalServerError) as e:
            print(f"Server Gemini sibuk/error (Percobaan {attempt + 1}): {e}")
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass
            
            if attempt < max_retries - 1:
                sleep_time = base_delay * (2 ** attempt)  # 2s, 4s, 8s...
                print(f"Menunggu {sleep_time} detik sebelum mencoba lagi...")
                time.sleep(sleep_time)
            else:
                print("Gemini menolak setelah semua percobaan.")
                raise HTTPException(status_code=503, detail=f"Gagal memproses video dengan Gemini API: {str(e)}")
                
        except Exception as e:
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass
            print(f"Terjadi kesalahan fatal pada Gemini: {e}")
            raise HTTPException(status_code=500, detail=f"Error internal Gemini: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "Clipper Project Backend is running smoothly."}

@app.post("/api/v1/generate-clip-url")
def generate_clip_url(payload: dict):
    video_url = payload.get("url")
    if not video_url:
        raise HTTPException(status_code=400, detail="URL YouTube tidak boleh kosong.")

    # Contoh titik integrasi pemanggilan fungsi di dalam endpoint FastAPI
    # (Pastikan path file hasil unduhan yt-dlp disesuaikan dengan logika unduhanmu)
    # mock_video_path = "./temp/sample_video.mp4"
    
    # ai_analysis = process_video_with_gemini(mock_video_path)
    
    return {
        "status": "success",
        "message": "Struktur logika siap dieksekusi."
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)