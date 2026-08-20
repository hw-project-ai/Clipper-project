import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    # Tambahkan baris ini untuk proksi Decodo-mu
    PROXY_URL = os.getenv("PROXY_URL") 
    
    MAX_VIDEO_LENGTH_SECONDS = 3600
    OUTPUT_DIR = "./output_clips"
    TEMP_DIR = "./temp"

settings = Settings()

os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
os.makedirs(settings.TEMP_DIR, exist_ok=True)