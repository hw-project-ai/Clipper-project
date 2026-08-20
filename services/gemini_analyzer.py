import json
import time
from google import genai
from google.genai import types
from config import settings

# Inisialisasi SDK terbaru Google GenAI
client = genai.Client(api_key=settings.GEMINI_API_KEY)

def analyze_and_get_highlights(video_path: str) -> dict:
    """Mengunggah video ke Gemini dan mengambil timestamp momen viral."""
    media_file = None
    try:
        # 1. Unggah media ke Gemini
        print(f"Mengunggah {video_path} ke Gemini...")
        media_file = client.files.upload(file=video_path)
        
        # Tunggu sebentar hingga file selesai diproses oleh Gemini (terutama jika file besar)
        time.sleep(3) 

        # 2. Prompt Sistem
        prompt = """
        Kamu adalah editor video viral profesional. Analisis konten audio dan visual dari video ini. 
        Temukan 1 segmen paling menarik, lucu, atau berpotensi viral (durasi 30-60 detik).
        
        Kembalikan hasilnya HANYA dalam format JSON murni:
        {
            "start_time_seconds": 15,
            "end_time_seconds": 45,
            "title": "Judul Hook TikTok",
            "reason": "Alasan singkat mengapa ini viral"
        }
        """

        # 3. Minta Gemini menghasilkan konten (memaksa output JSON)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[media_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )

        # 4. Parse respons
        result = json.loads(response.text)
        return result

    except Exception as e:
        raise Exception(f"Gagal memproses video dengan Gemini API: {str(e)}")
        
    finally:
        # 5. BERSIHKAN: Selalu hapus file dari server Google setelah selesai
        if media_file:
            try:
                client.files.delete(name=media_file.name)
                print("File media dihapus dari server Gemini.")
            except Exception as e:
                print(f"Gagal menghapus file di server Gemini: {e}")