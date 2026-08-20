import requests

# URL backend Render milikmu yang sudah aktif
url = "https://clipper-project-track8.onrender.com/api/v1/generate-clip"

# Pastikan nama file video ini sama persis dengan yang ada di folder
video_path = "Screenrecord.MP4"

print(f"Mengirim file {video_path} ke server Render...")

try:
    with open(video_path, "rb") as f:
        files = {"video": (video_path, f, "video/mp4")}
        response = requests.post(url, files=files)

    print(f"Status Code: {response.status_code}")
    print("Respons dari Server:")
    print(response.json())
except Exception as e:
    print(f"Terjadi kesalahan saat mengirim: {e}")