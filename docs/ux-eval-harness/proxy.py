"""Reverse-proxy sd01web01:8765, injecting a showPage() call for SPA screenshots."""
import http.client
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

UPSTREAM = ("sd01web01", 8765)
PAGE = sys.argv[1] if len(sys.argv) > 1 else "overview"
PORT = 8899


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        conn = http.client.HTTPConnection(*UPSTREAM, timeout=15)
        path = self.path
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        ctype = resp.getheader("Content-Type", "application/octet-stream")
        if "text/html" in ctype:
            html = body.decode("utf-8", "replace")
            inject = (
                "<script>window.addEventListener('load',()=>{"
                "setTimeout(()=>showPage('%s'),1500)});</script>" % PAGE
            )
            html = html.replace("</body>", inject + "</body>")
            body = html.encode("utf-8")
        self.send_response(resp.status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        conn.close()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()