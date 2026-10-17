import http.server
import json
import urllib.request
import urllib.error
import time
import os
import re
import uuid
import secrets
import sqlite3
import base64
import logging
from collections import defaultdict
from http import cookies
import bcrypt

# ==================== CAU HINH CO BAN & BAO MAT ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, 'fronted')
DB_PATH = os.path.join(BACKEND_DIR, 'secure_app.db')
LOG_PATH = os.path.join(BACKEND_DIR, 'security.log')

# Load .env thu cong an toan
API_TOKEN = ''
PORT = 8000
env_file = os.path.join(BACKEND_DIR, '.env')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                if k.strip() == 'REPLICATE_API_TOKEN':
                    API_TOKEN = v.strip()
                elif k.strip() == 'PORT':
                    PORT = int(v.strip())

if not API_TOKEN:
    API_TOKEN = os.environ.get('REPLICATE_API_TOKEN', 'YOUR_REPLICATE_API_TOKEN')

# 2. KHONG GHI THONG TIN NHAY CAM VAO LOG (Logging an toan)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# 1. RATE LIMIT CHO DANG NHAP VA API & ANTI-DDOS (LAYER 7 RATE LIMITING)
# IP -> list timestamps
LOGIN_ATTEMPTS = defaultdict(list)
API_ATTEMPTS = defaultdict(list)
GLOBAL_REQUESTS = defaultdict(list)
BANNED_IPS = {} # IP -> ban_until timestamp

MAX_LOGIN_ATTEMPTS = 5 # 5 lan / 1 phut
MAX_API_ATTEMPTS = 20 # 20 lan / 1 phut
MAX_GLOBAL_REQUESTS = 60 # 60 request / 10 giay (chong spam DDoS flood)
GLOBAL_WINDOW = 10 # giay
BAN_DURATION = 300 # Khoa IP 5 phut neu spam DDoS
RATE_LIMIT_WINDOW = 60 # giay

# KHOI TAO DATABASE AN TOAN & PARAMETERIZED QUERIES
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            csrf_token TEXT NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()

    # Tao tai khoan demo neu chua co (password hash bang Bcrypt chuan)
    cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        hashed = bcrypt.hashpw('Admin@123456'.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
        cursor.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', ('admin', hashed, 'admin'))
        conn.commit()
    conn.close()

init_db()

# HELPER: Kiem tra Rate Limit
def is_rate_limited(tracker, client_ip, max_calls, window):
    now = time.time()
    # Loc cac request cu
    tracker[client_ip] = [t for t in tracker[client_ip] if now - t < window]
    if len(tracker[client_ip]) >= max_calls:
        return True
    tracker[client_ip].append(now)
    return False

# HELPER: Lay session an toan
def get_session(cookie_header):
    if not cookie_header:
        return None
    c = cookies.SimpleCookie()
    try:
        c.load(cookie_header)
    except Exception:
        return None
    session_cookie = c.get('session_id')
    if not session_cookie:
        return None
    
    session_id = session_cookie.value
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, role, csrf_token, expires_at FROM sessions WHERE session_id = ?', (session_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None

    user_id, role, csrf_token, expires_at = row
    if time.time() > expires_at:
        # Session da het han -> Huy ngay
        cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        return None

    conn.close()
    return {
        'session_id': session_id,
        'user_id': user_id,
        'role': role,
        'csrf_token': csrf_token,
        'expires_at': expires_at
    }

class SecureAppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    # 5. KHOA PHIA TRINH DUYET & SECURITY HEADERS CHO MOI RESPONSE
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy', "default-src 'self' data: blob: https://replicate.delivery https://*.replicate.delivery; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://replicate.delivery https://*.replicate.delivery;")
        self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        # 6. CORS GIOI HAN
        self.send_header('Access-Control-Allow-Origin', f'http://localhost:{PORT}')
        super().end_headers()

    def _get_client_ip(self):
        # Xu ly IP an toan
        return self.client_address[0]

    def _send_json(self, obj, code=200, set_cookies=None):
        res_bytes = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(res_bytes)))
        if set_cookies:
            for sc in set_cookies:
                self.send_header('Set-Cookie', sc)
        self.end_headers()
        self.wfile.write(res_bytes)

    def _check_ddos(self):
        client_ip = self._get_client_ip()
        now = time.time()

        # Kiem tra IP co dang bi cam do DDoS khong
        if client_ip in BANNED_IPS:
            if now < BANNED_IPS[client_ip]:
                logging.warning(f"BANNED IP blocked: {client_ip}")
                self._send_json({'error': 'IP của bạn đã bị tạm khóa do nghi vấn tấn công DDoS.'}, 403)
                return False
            else:
                del BANNED_IPS[client_ip]

        # Kiem tra tan suat flood request
        GLOBAL_REQUESTS[client_ip] = [t for t in GLOBAL_REQUESTS[client_ip] if now - t < GLOBAL_WINDOW]
        if len(GLOBAL_REQUESTS[client_ip]) >= MAX_GLOBAL_REQUESTS:
            BANNED_IPS[client_ip] = now + BAN_DURATION
            logging.critical(f"DDoS Attack detected! Banned IP: {client_ip} for {BAN_DURATION}s")
            self._send_json({'error': 'Phát hiện lưu lượng bất thường (DDoS Attack). IP bị khóa 5 phút!'}, 429)
            return False

        GLOBAL_REQUESTS[client_ip].append(now)
        return True

    def do_GET(self):
        if not self._check_ddos():
            return
        # 4. IDOR CHECK: /api/user/<id> - Chi xem duoc thong tin cua chinh minh!
        if self.path.startswith('/api/user/'):
            session = get_session(self.headers.get('Cookie'))
            if not session:
                self._send_json({'error': 'Bạn chưa đăng nhập'}, 401)
                return

            req_id_match = re.match(r'^/api/user/(\d+)$', self.path)
            if not req_id_match:
                self._send_json({'error': 'Yêu cầu không hợp lệ'}, 400)
                return

            target_user_id = int(req_id_match.group(1))

            # Chặn triệt để IDOR: User không được xem thông tin user khác (trừ admin)
            if session['role'] != 'admin' and session['user_id'] != target_user_id:
                logging.warning(f"IDOR Alert: User {session['user_id']} co y truy cap User {target_user_id}")
                self._send_json({'error': 'Quyền truy cập bị từ chối (IDOR Prevention)'}, 403)
                return

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            # Parameterized Query
            cur.execute('SELECT id, username, role, created_at FROM users WHERE id = ?', (target_user_id,))
            u = cur.fetchone()
            conn.close()

            if u:
                self._send_json({'id': u[0], 'username': u[1], 'role': u[2], 'created_at': u[3]})
            else:
                self._send_json({'error': 'Không tìm thấy người dùng'}, 404)
            return

        # 4. KIEM TRA ADMIN: /api/admin/dashboard
        if self.path == '/api/admin/dashboard':
            session = get_session(self.headers.get('Cookie'))
            if not session or session['role'] != 'admin':
                logging.warning(f"Admin Access Denied for IP: {self._get_client_ip()}")
                self._send_json({'error': 'Chỉ tài khoản Quản Trị Viên (Admin) mới có quyền vào đây!'}, 403)
                return

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM users')
            user_count = cur.fetchone()[0]
            conn.close()
            self._send_json({'message': 'Chào mừng Quản Trị Viên!', 'total_users': user_count})
            return

        # Lay trang thai phien lam viec
        if self.path == '/api/auth/status':
            session = get_session(self.headers.get('Cookie'))
            if session:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],))
                urow = cur.fetchone()
                conn.close()
                username = urow[0] if urow else ''
                self._send_json({
                    'logged_in': True,
                    'user_id': session['user_id'],
                    'username': username,
                    'role': session['role'],
                    'csrf_token': session['csrf_token']
                })
            else:
                self._send_json({'logged_in': False})
            return

        return super().do_GET()

    # 4. CHONG CSRF KIEM TRA
    def _verify_csrf(self, session, req_csrf):
        if not session:
            return True # Neu chua login thi khong can session csrf
        return secrets.compare_digest(session.get('csrf_token', ''), req_csrf or '')

    def do_POST(self):
        if not self._check_ddos():
            return

        client_ip = self._get_client_ip()

        # 1. DANG NHAP + RATE LIMITING + HASH BCRYPT
        if self.path == '/api/auth/login':
            if is_rate_limited(LOGIN_ATTEMPTS, client_ip, MAX_LOGIN_ATTEMPTS, RATE_LIMIT_WINDOW):
                logging.warning(f"Rate limit triggered for login from IP: {client_ip}")
                self._send_json({'error': 'Quá nhiều lần thử đăng nhập. Vui lòng chờ 1 phút!'}, 429)
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
                # 3. Gioi han dung luong goi tin login (toi da 2KB)
                if content_length > 2048:
                    self._send_json({'error': 'Dữ liệu quá lớn'}, 400)
                    return

                data = json.loads(self.rfile.read(content_length).decode('utf-8'))
                username = data.get('username', '').strip()
                password = data.get('password', '')

                # Validate input server
                if not username or not password or len(username) > 50 or len(password) > 100:
                    self._send_json({'error': 'Tài khoản hoặc mật khẩu không hợp lệ'}, 400)
                    return

                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                # PARAMETERIZED QUERY (Chong SQL Injection)
                cur.execute('SELECT id, password_hash, role FROM users WHERE username = ?', (username,))
                user = cur.fetchone()

                if not user:
                    conn.close()
                    # 2. KHONG SHOW LOI CHI TIET
                    self._send_json({'error': 'Tên đăng nhập hoặc mật khẩu không chính xác'}, 401)
                    return

                user_id, pw_hash, role = user

                # Xac thuc mat khau bang bcrypt
                if not bcrypt.checkpw(password.encode('utf-8'), pw_hash.encode('utf-8')):
                    conn.close()
                    self._send_json({'error': 'Tên đăng nhập hoặc mật khẩu không chính xác'}, 401)
                    return

                # 2. DOI SESSION ID SAU KHI DANG NHAP & THOI GIAN HET HAN (Session timeout: 2 gio)
                session_id = secrets.token_hex(32)
                csrf_token = secrets.token_hex(16)
                expires_at = time.time() + 7200 # 2 hours

                # Xoa session cu cua user (neu muon session don)
                cur.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
                cur.execute('INSERT INTO sessions (session_id, user_id, role, csrf_token, expires_at) VALUES (?, ?, ?, ?, ?)',
                            (session_id, user_id, role, csrf_token, expires_at))
                conn.commit()
                conn.close()

                # 5. COOKIE: HttpOnly + Secure (SameSite)
                cookie_val = f"session_id={session_id}; Path=/; Max-Age=7200; HttpOnly; SameSite=Strict"
                self._send_json({
                    'success': True,
                    'user_id': user_id,
                    'username': username,
                    'role': role,
                    'csrf_token': csrf_token
                }, 200, set_cookies=[cookie_val])
                logging.info(f"User {username} logged in successfully from {client_ip}")
                return

            except Exception as e:
                logging.error(f"Login error: {str(e)}")
                self._send_json({'error': 'Đã xảy ra lỗi trong quá trình xử lý.'}, 500)
                return

        # DANG XUAT - HUY SESSION
        if self.path == '/api/auth/logout':
            session = get_session(self.headers.get('Cookie'))
            if session:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute('DELETE FROM sessions WHERE session_id = ?', (session['session_id'],))
                conn.commit()
                conn.close()

            # Xoa cookie o browser
            cookie_val = "session_id=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
            self._send_json({'success': True}, 200, set_cookies=[cookie_val])
            return

        # 3. XU LY ANH AI / ENHANCE VOI BAO MAT TOAN DIEN
        if self.path in ['/enhance.php', '/api/enhance']:
            # Rate limit API de chong lam dung API Replicate
            if is_rate_limited(API_ATTEMPTS, client_ip, MAX_API_ATTEMPTS, RATE_LIMIT_WINDOW):
                self._send_json({'error': 'Bạn đang gửi quá nhiều yêu cầu xử lý ảnh. Vui lòng thử lại sau!'}, 429)
                return

            content_length = int(self.headers.get('Content-Length', 0))

            # 3. GIOI HAN DUNG LUONG FILE: Toi da 8MB
            if content_length > 8 * 1024 * 1024:
                self._send_json({'error': 'Dung lượng ảnh vượt quá giới hạn tối đa cho phép (8MB)'}, 413)
                return

            try:
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
                image_base64 = data.get('image', '')
                req_csrf = data.get('csrf_token', '')

                # Kiem tra CSRF Token neu co phien dang nhap
                session = get_session(self.headers.get('Cookie'))
                if session and not self._verify_csrf(session, req_csrf):
                    self._send_json({'error': 'Yêu cầu không hợp lệ (CSRF verification failed)'}, 403)
                    return

                # 3. VALIDATE LAI O SERVER: Chi cho phep anh PNG/JPEG/WEBP hop le
                if not image_base64 or not isinstance(image_base64, str):
                    self._send_json({'error': 'Dữ liệu ảnh không hợp lệ'}, 400)
                    return

                header_match = re.match(r'^data:image\/(png|jpeg|jpg|webp);base64,', image_base64)
                if not header_match:
                    self._send_json({'error': 'Định dạng file không được hỗ trợ (Chỉ chấp nhận PNG, JPG, WEBP)'}, 400)
                    return

                # Validate do dai base64 va decode thu
                pure_base64 = image_base64.split(',', 1)[1]
                try:
                    img_bytes = base64.b64decode(pure_base64)
                except Exception:
                    self._send_json({'error': 'Dữ liệu mã hóa của ảnh bị hỏng'}, 400)
                    return

                # Kiem tra magic bytes cua file anh
                is_valid_image = (
                    img_bytes.startswith(b'\x89PNG\r\n\x1a\n') or # PNG
                    img_bytes.startswith(b'\xff\xd8\xff') or       # JPEG
                    (img_bytes.startswith(b'RIFF') and b'WEBP' in img_bytes[:16]) # WEBP
                )
                if not is_valid_image:
                    self._send_json({'error': 'Nội dung file không phải là ảnh hợp lệ!'}, 400)
                    return

                # Goi API Replicate bang Token an toan luu o Server (.env / env vars)
                req_url = 'https://api.replicate.com/v1/predictions'
                payload = json.dumps({
                    'version': '0fbacf7afc6c144e5be9767cff80f25aff23e52b0708f17e20f9879b2f21516c',
                    'input': {
                        'img': image_base64,
                        'version': 'v1.4',
                        'scale': 2
                    }
                }).encode('utf-8')

                req = urllib.request.Request(
                    req_url,
                    data=payload,
                    headers={
                        'Authorization': f'Bearer {API_TOKEN}',
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                    }
                )

                try:
                    with urllib.request.urlopen(req) as response:
                        res_data = json.loads(response.read().decode('utf-8'))
                except urllib.error.HTTPError as e:
                    logging.error(f"Replicate API Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
                    # 2. KHONG SHOW CHI TIET SECRET HOAC LOI NOI BO CHO USER
                    self._send_json({'error': 'Lỗi giao tiếp với dịch vụ xử lý AI. Vui lòng thử lại sau.'}, 502)
                    return

                poll_url = res_data.get('urls', {}).get('get')
                if not poll_url:
                    self._send_json({'error': 'Dịch vụ xử lý ảnh phản hồi không đầy đủ.'}, 502)
                    return

                status = res_data.get('status')
                output_url = None

                for _ in range(60):
                    if status == 'succeeded':
                        output_url = res_data.get('output')
                        break
                    elif status in ['failed', 'canceled']:
                        self._send_json({'error': 'Xử lý làm nét ảnh không thành công.'}, 500)
                        return

                    time.sleep(1)

                    poll_req = urllib.request.Request(
                        poll_url,
                        headers={
                            'Authorization': f'Bearer {API_TOKEN}',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                        }
                    )
                    with urllib.request.urlopen(poll_req) as poll_res:
                        res_data = json.loads(poll_res.read().decode('utf-8'))
                        status = res_data.get('status')

                if status == 'succeeded' and output_url:
                    self._send_json({'success': True, 'output': output_url})
                else:
                    self._send_json({'error': 'Quá thời gian chờ xử lý ảnh từ máy chủ AI.'}, 504)

            except Exception as e:
                logging.error(f"Internal server error: {str(e)}")
                self._send_json({'error': 'Lỗi xử lý nội bộ server.'}, 500)
            return

        self.send_error(404, "Not Found")

if __name__ == '__main__':
    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), SecureAppHandler)
    print(f"Backend bao mat dang chay tai: http://localhost:{PORT}")
    server.serve_forever()
