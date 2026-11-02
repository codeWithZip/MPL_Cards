# Standard-library-only local JSON payment database server.
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
import json, os, tempfile, threading, webbrowser, shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'database.json'
CARDS = ROOT / 'cards.json'
LOCK = threading.Lock()
LIMIT = 20 * 1024 * 1024

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args))

    def send(self, code, payload, mimetype):
        self.send_response(code)
        self.send_header('Content-Type', mimetype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/index.html'):
            self.send(200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ('/api/payments', '/api/cards'):
            with LOCK:
                try:
                    target = CARDS if path == '/api/cards' else DB
                    content = target.read_bytes() if target.exists() else b'[]'
                    obj = json.loads(content)
                    if not isinstance(obj, list):
                        raise ValueError('database.json must contain an array')
                    self.send(200, content, 'application/json; charset=utf-8')
                except (OSError, ValueError) as exc:
                    self.send(500, str(exc).encode(), 'text/plain; charset=utf-8')
        else:
            self.send(404, b'Not found', 'text/plain')

    def do_POST(self):
        if urlsplit(self.path).path not in ('/api/payments','/api/cards'):
            self.send(404, b'Not found', 'text/plain'); return
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if size < 0 or size > LIMIT:
                self.send(413, b'Invalid content length', 'text/plain'); return
            content = self.rfile.read(size)
            data = json.loads(content)
            if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
                raise ValueError('Expected array of payment objects')
            serialized = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            target = CARDS if urlsplit(self.path).path == '/api/cards' else DB
            with LOCK:
                fd, tmp = tempfile.mkstemp(prefix='.database-', suffix='.tmp', dir=ROOT)
                try:
                    with os.fdopen(fd, 'wb') as f:
                        f.write(serialized)
                        f.flush()
                        os.fsync(f.fileno())
                    if target.exists() and target.stat().st_size:
                        backup_dir = ROOT / 'backups'
                        backup_dir.mkdir(exist_ok=True)
                        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                        shutil.copy2(target, backup_dir / (target.stem + '_' + stamp + '.json'))
                    os.replace(tmp, target)
                finally:
                    if os.path.exists(tmp): os.unlink(tmp)
            self.send(200, b'{"ok":true}', 'application/json')
        except (ValueError, UnicodeDecodeError) as exc:
            self.send(400, str(exc).encode('utf-8'), 'text/plain; charset=utf-8')
        except OSError as exc:
            self.send(500, str(exc).encode('utf-8'), 'text/plain; charset=utf-8')

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    print('Your local database: ' + str(DB), flush=True)
    print('Open: http://127.0.0.1:8765', flush=True)
    print('Keep this window open while using the application.', flush=True)
    webbrowser.open('http://127.0.0.1:8765')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
