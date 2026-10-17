<?php
header('Content-Type: application/json; charset=utf-8');

// API Token Replicate
$apiToken = 'YOUR_REPLICATE_API_TOKEN';

// Nhan du lieu anh base64 tu client
$input = json_decode(file_get_contents('php://input'), true);

if (!isset($input['image'])) {
    echo json_encode(['error' => 'Thiếu dữ liệu ảnh']);
    exit;
}

$imageBase64 = $input['image'];

// Goi API Replicate su dung model GFPGAN (lam net anh khuon mat/chan dung)
$ch = curl_init('https://api.replicate.com/v1/predictions');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Authorization: Token ' . $apiToken,
    'Content-Type: application/json'
]);

$payload = [
    'version' => '9283608cc6453265fa2a15994fa5ab47b42e2c38ff977e5ae47837072423a4b1', // GFPGAN model version
    'input' => [
        'img' => $imageBase64,
        'version' => 'v1.4',
        'scale' => 2
    ]
];

curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
$response = curl_exec($ch);

if (curl_errno($ch)) {
    echo json_encode(['error' => 'cURL Error: ' . curl_error($ch)]);
    curl_close($ch);
    exit;
}

curl_close($ch);

$data = json_decode($response, true);

if (isset($data['error'])) {
    echo json_encode(['error' => $data['error']]);
    exit;
}

if (!isset($data['urls']['get'])) {
    echo json_encode(['error' => 'Không thể khởi tạo tiến trình xử lý ảnh: ' . $response]);
    exit;
}

$pollUrl = $data['urls']['get'];

// Cho ket qua xu ly (polling)
$status = $data['status'];
$outputUrl = null;

for ($i = 0; $i < 40; $i++) {
    if ($status === 'succeeded') {
        $outputUrl = $data['output'];
        break;
    } elseif ($status === 'failed' || $status === 'canceled') {
        echo json_encode(['error' => 'Xử lý làm nét ảnh thất bại trên server.']);
        exit;
    }

    sleep(1);

    $chPoll = curl_init($pollUrl);
    curl_setopt($chPoll, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($chPoll, CURLOPT_HTTPHEADER, [
        'Authorization: Token ' . $apiToken
    ]);
    $pollResponse = curl_exec($chPoll);
    curl_close($chPoll);

    $data = json_decode($pollResponse, true);
    $status = $data['status'] ?? 'failed';
}

if ($status === 'succeeded' && $outputUrl) {
    echo json_encode(['success' => true, 'output' => $outputUrl]);
} else {
    echo json_encode(['error' => 'Quá thời gian chờ xử lý ảnh hoặc chưa hoàn thành.']);
}
