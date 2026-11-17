"""MindRove Lab: device check + gesture recognition, served as a local web page.

    python app.py            real armband (join its Wi-Fi first, close MindRove Connect)
    python app.py --sim      simulated armband, no hardware needed

The page is fully self-contained (no internet needed), because while your computer is
on the armband's Wi-Fi it has no internet. On a headless Linux board run with
--host 0.0.0.0 --no-browser and open http://<board-ip>:8765 from another device.
"""
import argparse
import json
import queue
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from emg.engine import Engine
from emg.source import MindRoveSource, SimSource, parse_faults

ROOT = Path(__file__).parent
engine = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            q = engine.subscribe()
            try:
                while True:
                    try:
                        text = q.get(timeout=5)
                    except queue.Empty:
                        text = None
                    self.wfile.write(b": keepalive\n\n" if text is None else f"data: {text}\n\n".encode())
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                engine.unsubscribe(q)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/cmd":
            return self._send(404, b"not found", "text/plain")
        try:
            cmd = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if not isinstance(cmd, dict):
                raise ValueError
        except ValueError:
            return self._send(400, b"bad json", "text/plain")
        engine.command(cmd)
        self._send(200, b"{}", "application/json")


def main():
    global engine
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", action="store_true", help="use a simulated armband")
    ap.add_argument("--sim-faults", default="", metavar="LIST",
                    help="plant faults in the simulator, e.g. dead:3,hum:5,noisy:7,weak:2,drop")
    ap.add_argument("--mains", type=int, default=50, choices=(50, 60), help="mains frequency (UK/EU 50, US 60)")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach the page from other devices")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data-dir", default=None, help="default: data/, or data/sim/ with --sim")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    source = SimSource(parse_faults(args.sim_faults)) if args.sim else MindRoveSource()
    # Simulator recordings and models are kept apart so they can never be mistaken for,
    # or loaded as, results from the real armband.
    data_dir = args.data_dir or ROOT / "data" / ("sim" if args.sim else "")
    engine = Engine(source, mains=args.mains, data_dir=data_dir)
    engine.start()

    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print(f"MindRove Lab running at {url}   (source: {source.name})   Ctrl+C to stop")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        engine.join(timeout=5)   # lets the engine release the armband cleanly
        print("Stopped.")


if __name__ == "__main__":
    main()
