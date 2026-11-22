# ABOUTME: A local server that stands in for OpenAI, for the tests that use the real OpenAI client.
# ABOUTME: It answers with what the test gives it and records the requests it received.

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class OpenAIServer:
    """Answers every request with the same status and body, after an optional delay."""

    def __init__(self, intStatus, dctBody, fDelay=0):
        self.lstRequests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                binRequest = self.rfile.read(int(self.headers["Content-Length"]))
                owner.lstRequests.append((self.path, json.loads(binRequest)))
                time.sleep(fDelay)
                binBody = json.dumps(dctBody).encode()
                self.send_response(intStatus)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(binBody)))
                self.end_headers()
                self.wfile.write(binBody)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, args=(.01,), daemon=True).start()
        self.strUrl = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def start_openai_server():
    """Starts servers that are stopped when the test ends."""
    lstServers = []

    def start(intStatus, dctBody, fDelay=0):
        server = OpenAIServer(intStatus, dctBody, fDelay)
        lstServers.append(server)
        return server
    yield start
    for server in lstServers:
        server.stop()
