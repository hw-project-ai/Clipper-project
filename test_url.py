import requests
import json

# URL endpoint baru untuk scan link YouTube di Render milikmu
url = "https://clipper-project-track8.onrender.com/api/v1/generate-clip-url"

# Masukkan link video YouTube pendek apa saja yang ingin diuji
payload = {
    "url": "https://youtu.be/ywx_PwoS4YE?is=Ki3ww6qfrg6AVCzv"
}

print("Mengirim URL YouTube ke server Render...")
print("AI sedang merayapi link, mengunduh audio/video, dan mencari highlight...")

try:
    # Mengirim request POST dengan format JSON
    response = requests.post(url, json=payload, timeout=300)

    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        print("Berhasil! Respons JSON dari Server:")
        print(json.dumps(response.json(), indent=2))
    else:
        print("Server merespons dengan error:")
        print(response.text)

except requests.exceptions.Timeout:
    print("Waktu habis (Timeout): Proses unduh dan analisis YouTube memakan waktu terlalu lama.")
except Exception as e:
    print(f"Terjadi kesalahan koneksi: {e}")