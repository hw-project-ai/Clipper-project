import requests
import time
import json

# URL endpoint server Render milikmu
BASE_URL = "https://clipper-project-track8.onrender.com"
GENERATE_URL = f"{BASE_URL}/api/v1/generate-clip-url"

# Masukkan link video YouTube
payload = {
    "url": "https://youtu.be/xEah8NzNrGQ?si=gCI0153cI9onYk47"
}

print("Mengirim URL YouTube ke server Render...")
print("Memulai tugas di latar belakang...")

try:
    # Mengirim request POST awal untuk mendapatkan job_id
    response = requests.post(GENERATE_URL, json=payload, timeout=30)

    print(f"\nStatus Code (Inisiasi): {response.status_code}")
    
    if response.status_code == 200:
        res_data = response.json()
        job_id = res_data.get("job_id")
        print(f"Berhasil! Job ID didapatkan: {job_id}")
        print("AI sedang merayapi link, mengunduh, dan memotong klip di latar belakang...\n")
        
        # Melakukan polling status secara berkala ke server
        status_url = f"{BASE_URL}/api/v1/status/{job_id}"
        
        while True:
            time.sleep(5) # Tunggu 5 detik setiap kali cek
            status_res = requests.get(status_url, timeout=10)
            
            if status_res.status_code == 200:
                status_data = status_res.json()
                current_status = status_data.get("status")
                current_msg = status_data.get("message")
                
                print(f"Status saat ini: [{current_status.upper()}] - {current_msg}")
                
                if current_status == "completed":
                    print("\nProses sepenuhnya berhasil! Respons dari Server:")
                    print(json.dumps(status_data, indent=2))
                    break
                elif current_status == "failed":
                    print(f"\nProses di latar belakang gagal: {current_msg}")
                    break
            else:
                print(f"Gagal memeriksa status: {status_res.status_code}")
                break
    else:
        print("Server merespons dengan error saat inisiasi:")
        print(response.text)

except requests.exceptions.Timeout:
    print("Waktu habis (Timeout): Koneksi awal memakan waktu terlalu lama.")
except requests.exceptions.ConnectionError:
    print("Kesalahan Koneksi: Gagal terhubung ke server Render. Pastikan server aktif.")
except Exception as e:
    print(f"Terjadi kesalahan yang tidak terduga: {e}")