# Menggunakan image Python yang ringan
FROM python:3.10-slim

# INI BAGIAN PALING PENTING: Menginstal FFmpeg di sistem server
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

# Menentukan direktori kerja di dalam server
WORKDIR /app

# Meng-copy file requirements.txt
COPY requirements.txt .

# Menginstal semua pustaka Python (FastAPI, dll)
RUN pip install --no-cache-dir -r requirements.txt

# Meng-copy seluruh sisa kodemu ke dalam server
COPY . .

# Membuka port 8000 untuk FastAPI
EXPOSE 8000

# Perintah untuk menjalankan server aplikasimu
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]