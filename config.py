import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    MAX_VIDEO_LENGTH_SECONDS = 3600
    OUTPUT_DIR = "./output_clips"
    TEMP_DIR = "./temp"

settings = Settings()

# Pastikan folder tersedia
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
os.makedirs(settings.TEMP_DIR, exist_ok=True)