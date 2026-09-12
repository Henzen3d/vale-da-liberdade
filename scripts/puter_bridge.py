import os
import json
import ssl
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

PUTER_TOKEN = os.environ.get("PUTER_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InYyIn0.eyJ0IjoidCIsInYiOiIyIiwidG9rZW5fdWlkIjoiOWQwYmIxMjQtZjg3My00YmZmLWJhNDQtOTZiMzExYzhjOWFlIiwidXUiOiJFNXlETkZna1JJYXo2ZWxNOWloQkVBPT0iLCJzdSI6Ik5OV2tLR21TUjM2YThWNTlVdXRWUFE9PSIsImFpIjoiRTV5RE5GZ2tSSWF6NmVsTTlpaEJFQT09IiwiZnVsbF9hY2Nlc3MiOnRydWUsImlhdCI6MTc4NzEwMDc4N30.fZvbM4Q3lgh8vfZpu49xYED5m717TnomtRMkF0Wltfg")

class PuterProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            req_data = json.loads(body.decode('utf-8'))
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')
            return

        model = req_data.get('model', 'claude-opus-5')
        messages = req_data.get('messages', [])

        puter_payload = {
            "interface": "puter-chat-completion",
            "driver": "ai-chat",
            "test_mode": False,
            "method": "complete",
            "args": {
                "messages": messages,
                "model": model
            }
        }

        puter_req = urllib.request.Request(
            "https://api.puter.com/drivers/call",
            data=json.dumps(puter_payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {PUTER_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
        )

        try:
            with urllib.request.urlopen(puter_req, context=ctx, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                
                result = data.get("result", {})
                content = ""
                
                if "message" in result and isinstance(result["message"], dict):
                    # Anthropic style
                    content_blocks = result["message"].get("content", [])
                    if isinstance(content_blocks, list):
                        content = "".join([b.get("text", "") for b in content_blocks if isinstance(b, dict)])
                    elif isinstance(content_blocks, str):
                        content = content_blocks
                elif "message" in result and "content" in result["message"]:
                    # OpenAI style
                    content = result["message"]["content"]
                elif "text" in result:
                    content = result["text"]

                openai_response = {
                    "id": "chatcmpl-puter-" + os.urandom(6).hex(),
                    "object": "chat.completion",
                    "created": 1787101000,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": len(content.split()),
                        "total_tokens": 100 + len(content.split())
                    }
                }

                resp_bytes = json.dumps(openai_response).encode('utf-8')
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                self.wfile.write(resp_bytes)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            err_obj = {"error": {"message": str(e), "type": "puter_proxy_error"}}
            self.wfile.write(json.dumps(err_obj).encode('utf-8'))

    def do_GET(self):
        if self.path.endswith('/models') or self.path == '/v1/models':
            models_list = {
                "object": "list",
                "data": [
                    {"id": "claude-opus-5", "object": "model", "owned_by": "anthropic"},
                    {"id": "claude-opus-4-6", "object": "model", "owned_by": "anthropic"},
                    {"id": "claude-sonnet-4-6", "object": "model", "owned_by": "anthropic"},
                    {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
                    {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
                    {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"}
                ]
            }
            resp_bytes = json.dumps(models_list).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format, *args):
        # Silenciar logs na saída padrão
        return

def run_server(port=9455):
    server = HTTPServer(('127.0.0.1', port), PuterProxyHandler)
    print(f"Puter OpenAI Proxy running on http://127.0.0.1:{port}")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
