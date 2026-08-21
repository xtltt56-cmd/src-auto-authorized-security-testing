"""Small operator-started loopback fixture; it never binds to a non-loopback address."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple


class Handler(BaseHTTPRequestHandler):
    server_version = "SRC-Auto-Lab/1.0"

    def do_GET(self):  # noqa: N802 - stdlib handler API
        body = b"SRC-Auto local lab\n" if self.path == "/" else b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Deliberately omit X-Content-Type-Options for a passive fixture finding.
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - stdlib handler API
        return


def serve(port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("SRC-Auto local lab listening on http://127.0.0.1:{}".format(port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
