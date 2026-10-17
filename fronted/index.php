<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Web Camera Thiet Bi</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <h1>Ứng Dụng Camera Thiết Bị</h1>
        <p class="subtitle">Lấy trực tiếp luồng video từ camera của thiết bị của bạn</p>

        <div class="video-wrapper">
            <video id="cameraFeed" autoplay playsinline></video>
            <canvas id="photoCanvas" style="display: none;"></canvas>
        </div>

        <div class="controls">
            <button id="btnStart" class="btn btn-primary">Bật Camera</button>
            <button id="btnFlip" class="btn btn-info">Lật Gương (Soi Gương)</button>
            <button id="btnCapture" class="btn btn-success" disabled>Chụp Ảnh</button>
            <button id="btnEnhance" class="btn btn-warning" disabled>Làm Nét Ảnh (AI)</button>
            <button id="btnStop" class="btn btn-danger" disabled>Tắt Camera</button>
        </div>

        <div id="loadingStatus" style="display: none; margin: 15px 0; font-weight: bold; color: #007bff;">
            Đang xử lý làm nét ảnh qua AI, vui lòng chờ...
        </div>

        <div class="preview-area" id="previewArea" style="display: none;">
            <div class="image-comparison">
                <div class="image-box">
                    <h3>Ảnh Gốc Chụp:</h3>
                    <img id="photoPreview" alt="Ảnh chụp từ camera">
                    <div class="image-actions">
                        <button id="btnSave" class="btn btn-save">Lưu vào thiết bị</button>
                        <button id="btnDelete" class="btn btn-delete">Xóa ảnh này</button>
                        <button id="btnReset" class="btn btn-reset">Reset toàn bộ</button>
                    </div>
                </div>
                <div class="image-box" id="enhancedBox" style="display: none;">
                    <h3>Ảnh Đã Làm Nét:</h3>
                    <img id="photoEnhanced" alt="Ảnh sau khi làm nét">
                </div>
            </div>
        </div>
    </div>

    <script src="script.js"></script>
</body>
</html>
