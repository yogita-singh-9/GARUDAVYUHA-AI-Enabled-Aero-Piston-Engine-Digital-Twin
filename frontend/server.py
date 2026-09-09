"""
GARUDAVYUHA – Digital Twin GCS Dedicated Python Server
Serves all application files with proper MIME types for 3D GLTF models, Brython Python files, and assets.
Usage:
    py server.py [--port 8080] [--no-browser]
"""

import http.server
import socketserver
import os
import sys
import webbrowser
import argparse

root_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8080

sys.path.insert(0, os.path.join(root_dir, 'py'))
sys.path.insert(0, os.path.join(root_dir, 'backend'))

try:
    from server_api import GCSAPIHandler
    GCSHTTPRequestHandler = GCSAPIHandler
    print("[GARUDAVYUHA Server] GCSAPIHandler loaded successfully.")
except Exception as err:
    print("[GARUDAVYUHA Server] Note: GCSAPIHandler fallback trigger:", err)
    GCSHTTPRequestHandler = http.server.SimpleHTTPRequestHandler


def run_server(port=DEFAULT_PORT, open_browser=True):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = GCSHTTPRequestHandler

    class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        with ReusableTCPServer(("", port), handler) as httpd:
            url = f"http://localhost:{port}/index.html"
            print("=" * 70)
            print("  GARUDAVYUHA: AI-ENABLED ENGINE DIGITAL TWIN (SIH 2026)")
            print("  Ground Control Station Server Online")
            print(f"  URL: {url}")
            print(f"  Root: {os.getcwd()}")
            print(f"  RequestHandler: {handler.__name__}")
            print("  Press Ctrl+C to terminate server")
            print("=" * 70)

            if open_browser:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass

            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[GARUDAVYUHA] GCS Server stopped gracefully.")
        sys.exit(0)
    except OSError as e:
        print(f"[ERROR] Port {port} could not be bound: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GARUDAVYUHA GCS Python Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    args = parser.parse_args()

    run_server(port=args.port, open_browser=not args.no_browser)
