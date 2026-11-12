import json

import queue
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "oc-mcp", "version": "0.1.0"}
DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "bridge.log"



def rpc_result(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class Bridge:
    def __init__(self, tools, host="127.0.0.1", port=8765, log_file=None, world_id=None):
        self.tools = {tool.name: tool for tool in tools}
        self.world_id = world_id
        self.host = host
        self.port = port
        self.log_file = Path(log_file or DEFAULT_LOG_FILE)
        self._commands = queue.Queue()
        self._results = {}
        self._results_condition = threading.Condition()

    def log(self, message):
        with self.log_file.open("a") as f:
            f.write(message + "\n")


    def start_http_server(self):
        server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def _next_command(self):
        try:
            return self._commands.get_nowait()
        except queue.Empty:
            return None

    def _store_result(self, result):
        with self._results_condition:
            self._results[result["id"]] = result
            self._results_condition.notify_all()

    def _wait_for_result(self, command_id, timeout):
        with self._results_condition:
            self._results_condition.wait_for(lambda: command_id in self._results, timeout)
            return self._results.pop(command_id, None)

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _json(self, status, body):
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                bridge.log(f"GET {self.path}")
                if self.path != "/poll":
                    self._json(404, {"error": "not found"})
                    return
                self._json(200, {"command": bridge._next_command()})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(length).decode(errors="replace")
                bridge.log(f"POST {self.path} {body[:200]}")
                if self.path != "/result":
                    self._json(404, {"error": "not found"})
                    return
                try:
                    result = json.loads(body)
                    result["id"]
                except (ValueError, KeyError, TypeError):
                    self._json(400, {"error": "invalid result"})
                    return
                bridge._store_result(result)
                self._json(200, {"ok": True})

        return Handler


    def handle_rpc(self, request):
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            return rpc_result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return rpc_result(request_id, {"tools": [
                {"name": t.name, "description": t.description, "inputSchema": t.schema()}
                for t in self.tools.values()]})
        if method == "tools/call":
            return self._call_tool(request_id, request.get("params", {}))
        return rpc_error(request_id, -32601, "method not found")

    def _call_tool(self, request_id, params):
        tool = self.tools.get(params.get("name"))
        if tool is None:
            return rpc_error(request_id, -32602, "unknown tool")
        arguments = params.get("arguments", {})
        argument_error = tool.validate(arguments)
        if argument_error:
            return rpc_error(request_id, -32602, argument_error)
        command_id = uuid.uuid4().hex
        self._commands.put({"id": command_id, "type": tool.name,
                            **tool.prepare(arguments), **tool.context(self)})
        result = self._wait_for_result(command_id, tool.timeout)
        if result is None:
            return rpc_error(request_id, -32000,
                             f"OpenComputers did not respond within {tool.timeout:g}s. The command may still "
                             "run later (singleplayer pauses when the game window loses focus): check the state, "
                             "e.g. with inventory_scan, before retrying.")
        if not result.get("ok"):
            return rpc_error(request_id, -32001, result.get("error", "command failed"))
        return rpc_result(request_id, {
            "content": [{"type": "text", "text": result.get("text", "Done.")}]})

    def serve_stdio(self):
        self.start_http_server()
        for line in sys.stdin:
            try:
                response = self.handle_rpc(json.loads(line))
            except json.JSONDecodeError:
                response = rpc_error(None, -32700, "parse error")
            if response is not None:
                print(json.dumps(response), flush=True)
