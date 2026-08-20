// clipper-cobalt.js
// Dirancang khusus untuk berkomunikasi dengan Opus Clip Clone API milikmu.

class ClipperCobalt {
    constructor(config) {
        // Secara default, arahkan ke localhost tempat FastAPI berjalan (port 8000)
        this.apiUrl = config.apiUrl || "http://localhost:8000/api/v1";
        this.isProcessing = false;
    }

    /**
     * Mengirim URL YouTube ke FastAPI backend untuk diproses.
     * @param {string} videoUrl - URL video yang akan dipotong.
     * @returns {Promise<Object>} - Mengembalikan data highlight dan link unduhan.
     */
    async generateClip(videoUrl) {
        if (this.isProcessing) {
            throw new Error("Clipper is currently processing another video. Please wait.");
        }

        if (!videoUrl || typeof videoUrl !== 'string') {
            throw new Error("Invalid video URL provided.");
        }

        this.isProcessing = true;
        console.log(`[ClipperCobalt] Sending URL to backend: ${videoUrl}`);

        try {
            // Melakukan request POST ke endpoint FastAPI-mu
            const response = await fetch(`${this.apiUrl}/generate-clip-url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                // Payload disesuaikan dengan model pydantic VideoURL di main.py
                body: JSON.stringify({ url: videoUrl })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Server Error: ${errorData.detail || response.statusText}`);
            }

            const result = await response.json();

            // Result akan berisi { status, data, download_url } dari main.py
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
        // Mengubah path relatif menjadi URL absolut ke backend
        const fullUrl = `http://localhost:8000${downloadPath}`;
        const a = document.createElement('a');
        a.href = fullUrl;
        a.download = downloadPath.split('/').pop(); // Mengambil nama file
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

// Mengekspor instance default
export const cobaltInstance = new ClipperCobalt({
    apiUrl: "http://localhost:8000/api/v1"
});

export default ClipperCobalt;