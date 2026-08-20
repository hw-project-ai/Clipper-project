import requests
import time
import json

# URL endpoint server Render
BASE_URL = "https://clipper-project-track8.onrender.com"
GENERATE_URL = f"{BASE_URL}/api/v1/generate-clip-url"

payload = {
    "url": "https://youtu.be/xEah8NzNrGQ?si=gCI0153cI9onYk47"
}

print("Mengirim URL ke server, memulai proses latar belakang...")
response = requests.post(GENERATE_URL, json=payload)

if response.status_code == 200:
    data = response.json()
    job_id = data["job_id"]
    print(f"Pekerjaan dimulai! Job ID: {job_id}")
    
    # Polling status secara berkala
    while True:
        print("Memeriksa status...")
        try:
            status_res = requests.get(f"{BASE_URL}/api/v1/status/{job_id}")
            status_data = status_res.json()
            
            print(f"Status: {status_data['status']} - {status_data['message']}")
            
            if status_data["status"] == "completed":
                print("\nProses selesai! Berikut hasilnya:")
                print(json.dumps(status_data, indent=2))
                break
            elif status_data["status"] == "failed":
                print(f"\nProses gagal: {status_data['message']}")
                break
        except Exception as e:
            print(f"Gagal memeriksa status: {e}")
        
        # Tunggu 5 detik sebelum mencoba lagi agar tidak membebani server
        time.sleep(5) 
else:
    print(f"Gagal mengirim request: {response.status_code}")
    print(response.text)