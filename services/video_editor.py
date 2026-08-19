import ffmpeg
import os
from config import settings

def crop_and_cut_video(input_path: str, start_time: int, end_time: int, output_filename: str) -> str:
    """Memotong video dan mengubah rasio menjadi 9:16."""
    output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    
    try:
        (
            ffmpeg
            .input(input_path, ss=start_time, to=end_time)
            .filter('crop', 'ih*9/16', 'ih') # Rasio TikTok/Reels
            .filter('scale', 1080, 1920)
            .output(output_path, c_v='libx264', c_a='aac', strict='experimental')
            .overwrite_output()
            .run(quiet=True)
        )
        return output_path
    except ffmpeg.Error as e:
        raise Exception(f"Error FFmpeg: {e.stderr.decode() if e.stderr else str(e)}")