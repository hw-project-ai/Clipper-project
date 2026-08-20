// clipper-cobalt.js
// Dirancang khusus untuk berkomunikasi dengan Opus Clip Clone API milikmu.
// Pembaruan: Dukungan Resolusi Kustom

class ClipperCobalt {
    constructor(config) {
        // Arahkan ke URL Render-mu saat produksi, atau localhost saat pengujian lokal
        this.apiUrl = config.apiUrl || "https://clipper-project-track8.onrender.com/api/v1";
        this.isProcessing = false;
    }

    /**
     * Mengirim URL YouTube dan resolusi target ke FastAPI backend untuk diproses.
     * @param {string} videoUrl - URL video yang akan dipotong.
     * @param {string} resolution - Kualitas resolusi target (contoh: "720", "1080", atau "best"). Default "best".
     * @returns {Promise<Object>} - Mengembalikan data highlight dan link unduhan.
     */
    async generateClip(videoUrl, resolution = "best") {
        if (this.isProcessing) {
            throw new Error("Clipper is currently processing another video. Please wait.");
        }

        if (!videoUrl || typeof videoUrl !== 'string') {
            throw new Error("Invalid video URL provided.");
        }

        this.isProcessing = true;
        console.log(`[ClipperCobalt] Sending URL to backend: ${videoUrl} with resolution: ${resolution}`);

        try {
            // Melakukan request POST ke endpoint FastAPI-mu
            const response = await fetch(`${this.apiUrl}/generate-clip-url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                // Payload sekarang menyertakan resolusi sesuai model VideoURL di main.py
                body: JSON.stringify({
                    url: videoUrl,
                    resolution: resolution
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Server Error: ${errorData.detail || response.statusText}`);
            }

            const result = await response.json();

            console.log("[ClipperCobalt] Clip generated successfully!", result);
            return result;

        } catch (error) {
            console.error("[ClipperCobalt] Failed to generate clip:", error.message);
            throw error;
        } finally {
            this.isProcessing = false;
        }
    }

    /**
     * Fungsi utilitas untuk membuat elemen unduhan secara otomatis di browser
     * @param {string} downloadPath - Path relatif dari backend (/files/nama_video.mp4)
     */
    triggerDownload(downloadPath) {
        // Mengubah path relatif menjadi URL absolut ke backend Render-mu
        // Pastikan ini menggunakan domain Render, bukan localhost, jika backend di cloud
        const baseUrl = this.apiUrl.replace('/api/v1', '');
        const fullUrl = `${baseUrl}${downloadPath}`;

        const a = document.createElement('a');
        a.href = fullUrl;
        a.download = downloadPath.split('/').pop(); // Mengambil nama file
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

// Mengekspor instance default (Pastikan URL ini mengarah ke Render-mu)
export const cobaltInstance = new ClipperCobalt({
    apiUrl: "https://clipper-project-track8.onrender.com/api/v1"
});

export default ClipperCobalt;