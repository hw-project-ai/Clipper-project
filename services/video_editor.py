import ffmpeg
import os
from config import settings

def crop_and_cut_video(input_path: str, start_time: int, end_time: int, output_filename: str) -> str:
    """Memotong video dan menyesuaikan rasio 9:16 secara aman menggunakan FFmpeg."""
    output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    
    try:
        # Probe video untuk mendapatkan lebar dan tinggi asli secara otomatis
        probe = ffmpeg.probe(input_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        
        # Hitung ukuran crop vertikal yang aman berdasarkan dimensi asli video
        # Jika video sudah vertikal atau horizontal, kita ambil bagian tengahnya
        target_width = int(height * 9 / 16)
        if target_width > width:
            target_width = width
            target_height = int(width * 16 / 9)
        else:
            target_height = height

        input_stream = ffmpeg.input(input_path, ss=start_time, to=end_time)
        
        # Proses pipeline FFmpeg dengan ukuran dinamis
        (
            input_stream
            .filter('crop', target_width, target_height, '(in_w-out_w)/2', '(in_h-out_h)/2')
            .filter('scale', 1080, 1920)
            .output(output_path, **{'c:v': 'libx264', 'c:a': 'aac'}, strict='experimental')
            .overwrite_output()
            .run(quiet=True)
        )
        return output_path
        
    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else str(e)
        raise Exception(f"Error FFmpeg: {error_message}")