import requests
import json

# URL endpoint server Render milikmu
url = "https://clipper-project-track8.onrender.com/api/v1/generate-clip-url"

# Masukkan link video YouTube yang ingin diuji
payload = {
    "url": "https://youtu.be/ywx_PwoS4YE?is=Ki3ww6qfrg6AVCzv"
}

print("Mengirim URL YouTube ke server Render...")
print("AI sedang merayapi link, mengunduh audio/video, dan mencari highlight...")

try:
    # Mengirim request POST dengan format JSON dan timeout yang memadai untuk proses video
    response = requests.post(url, json=payload, timeout=300)

    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        res_data = response.json()
        print("Berhasil! Respons JSON dari Server:")
        print(json.dumps(res_data, indent=2))
        
        # Ekstraksi informasi penting jika tersedia
        if "download_url" in res_data:
            print(f"\nLink Unduhan Video Klip: https://clipper-project-track8.onrender.com{res_data['download_url']}")
    else:
        print("Server merespons dengan error:")
        print(response.text)

except requests.exceptions.Timeout:
    print("Waktu habis (Timeout): Proses unduh dan analisis YouTube memakan waktu terlalu lama di server.")
except requests.exceptions.ConnectionError:
    print("Kesalahan Koneksi: Gagal terhubung ke server Render. Pastikan server aktif dan URL benar.")
except Exception as e:
    print(f"Terjadi kesalahan yang tidak terduga: {e}")