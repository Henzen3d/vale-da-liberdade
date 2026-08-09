import os
import re
import sys
import functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

class RangeHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def do_GET(self):
        range_header = self.headers.get('Range') or self.headers.get('range')
        if range_header:
            self.handle_range(range_header)
        else:
            super().do_GET()

    def handle_range(self, range_header):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404, "File not found")
            return

        size = os.path.getsize(path)
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if not match:
            super().do_GET()
            return

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
        if start >= size:
            self.send_error(416, "Requested Range Not Satisfiable")
            return

        end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        try:
            with open(path, 'rb') as f:
                f.seek(start)
                buf_size = 64 * 1024
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(buf_size, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            pass

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    print(f"Servidor HTTP Multithreaded com suporte a Range Requests rodando na porta {port}...")
    handler_class = functools.partial(RangeHTTPRequestHandler, directory="public")
    server = ThreadingHTTPServer(('0.0.0.0', port), handler_class)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
