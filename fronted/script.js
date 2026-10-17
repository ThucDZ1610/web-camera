// ==================== ANTI CRACK / ANTI F12 & DEVTOOLS ====================
// 1. Chan chuot phai (Context Menu)
document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
}, false);

// 2. Chan cac phim tat: F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U, Ctrl+S
document.addEventListener('keydown', function (e) {
    if (
        e.key === 'F12' ||
        (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'i' || e.key === 'J' || e.key === 'j' || e.key === 'C' || e.key === 'c')) ||
        (e.ctrlKey && (e.key === 'u' || e.key === 'U' || e.key === 's' || e.key === 'S'))
    ) {
        e.preventDefault();
        e.stopPropagation();
        return false;
    }
}, false);

// 3. Phat hien DevTools mo bang Debugger Loop & Window Threshold
(function antiDevTools() {
    function detect() {
        const threshold = 160;
        const widthThreshold = window.outerWidth - window.innerWidth > threshold;
        const heightThreshold = window.outerHeight - window.innerHeight > threshold;
        
        if (widthThreshold || heightThreshold) {
            document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;background:#111;color:#ff4444;font-family:sans-serif;font-size:20px;font-weight:bold;">CANH BAO: Che do kiem tra phan tu (DevTools) bi cam tren trang web nay!</div>';
        }
    }
    window.addEventListener('resize', detect);
    setInterval(detect, 1000);
})();

const cameraFeed = document.getElementById('cameraFeed');
const photoCanvas = document.getElementById('photoCanvas');
const photoPreview = document.getElementById('photoPreview');
const photoEnhanced = document.getElementById('photoEnhanced');
const previewArea = document.getElementById('previewArea');
const enhancedBox = document.getElementById('enhancedBox');
const loadingStatus = document.getElementById('loadingStatus');

const btnStart = document.getElementById('btnStart');
const btnFlip = document.getElementById('btnFlip');
const btnCapture = document.getElementById('btnCapture');
const btnEnhance = document.getElementById('btnEnhance');
const btnStop = document.getElementById('btnStop');

const btnSave = document.getElementById('btnSave');
const btnDelete = document.getElementById('btnDelete');
const btnReset = document.getElementById('btnReset');

let stream = null;
let currentImageData = null;
let isFlipped = true; // Mac dinh lat guong nhu camera truoc/guong

// Ap dung lat guong mac dinh
cameraFeed.classList.add('flipped');

// Xu ly nut lat camera / soi guong
function toggleFlip() {
    isFlipped = !isFlipped;
    if (isFlipped) {
        cameraFeed.classList.add('flipped');
        btnFlip.textContent = 'Bỏ Lật Gương';
    } else {
        cameraFeed.classList.remove('flipped');
        btnFlip.textContent = 'Lật Gương (Soi Gương)';
    }
}

// Bat camera tu thiet bi
async function startCamera() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: 'user'
            },
            audio: false
        });

        cameraFeed.srcObject = stream;
        btnStart.disabled = true;
        btnCapture.disabled = false;
        btnStop.disabled = false;
    } catch (error) {
        alert('Khong the truy cap camera thiet bi: ' + error.message);
    }
}

// Chup anh tu camera
function capturePhoto() {
    if (!stream) return;

    photoCanvas.width = cameraFeed.videoWidth;
    photoCanvas.height = cameraFeed.videoHeight;

    const ctx = photoCanvas.getContext('2d');

    if (isFlipped) {
        ctx.translate(photoCanvas.width, 0);
        ctx.scale(-1, 1);
    }

    ctx.drawImage(cameraFeed, 0, 0, photoCanvas.width, photoCanvas.height);

    currentImageData = photoCanvas.toDataURL('image/png');
    photoPreview.src = currentImageData;
    previewArea.style.display = 'block';
    enhancedBox.style.display = 'none';
    btnEnhance.disabled = false;
}

let csrfToken = '';
const BACKEND_API_URL = 'https://web-camera-cst9.onrender.com';

// Kiem tra trang thai auth va lay CSRF token
fetch(`${BACKEND_API_URL}/api/auth/status`)
    .then(res => res.json())
    .then(data => {
        if (data.logged_in && data.csrf_token) {
            csrfToken = data.csrf_token;
        }
    })
    .catch(() => {});

// Lam net anh qua AI
async function enhancePhoto() {
    if (!currentImageData) {
        alert('Vui lòng chụp ảnh trước!');
        return;
    }

    loadingStatus.style.display = 'block';
    btnEnhance.disabled = true;

    try {
        const response = await fetch(`${BACKEND_API_URL}/api/enhance`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                image: currentImageData,
                csrf_token: csrfToken
            })
        });

        const result = await response.json();

        if (result.success && result.output) {
            photoEnhanced.src = result.output;
            enhancedBox.style.display = 'block';
        } else {
            alert('Lỗi làm nét: ' + (result.error || 'Không xác định'));
        }
    } catch (err) {
        alert('Lỗi kết nối tới server làm nét: ' + err.message);
    } finally {
        loadingStatus.style.display = 'none';
        btnEnhance.disabled = false;
    }
}

// Tat camera thiet bi
function stopCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        cameraFeed.srcObject = null;
        stream = null;
    }

    btnStart.disabled = false;
    btnCapture.disabled = true;
    btnStop.disabled = true;
}

// Luu anh goc vao thiet bi
function savePhoto() {
    if (!currentImageData) return;
    const link = document.createElement('a');
    link.href = currentImageData;
    link.download = 'anh_chup_camera_' + Date.now() + '.png';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Xoa anh goc hien tai
function deletePhoto() {
    currentImageData = null;
    photoPreview.removeAttribute('src');
    
    // Neu co anh lam net thi giu lai hoac an toan bo neu khong co gi
    if (enhancedBox.style.display === 'none') {
        previewArea.style.display = 'none';
    }
    btnEnhance.disabled = true;
}

// Reset toan bo anh ve ban dau (0 anh)
function resetAll() {
    currentImageData = null;
    photoPreview.removeAttribute('src');
    photoEnhanced.removeAttribute('src');
    enhancedBox.style.display = 'none';
    previewArea.style.display = 'none';
    btnEnhance.disabled = true;
}

btnStart.addEventListener('click', startCamera);
btnFlip.addEventListener('click', toggleFlip);
btnCapture.addEventListener('click', capturePhoto);
btnEnhance.addEventListener('click', enhancePhoto);
btnStop.addEventListener('click', stopCamera);

btnSave.addEventListener('click', savePhoto);
btnDelete.addEventListener('click', deletePhoto);
btnReset.addEventListener('click', resetAll);
