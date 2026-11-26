"""Exercise the release CLI with real HTTPS on a disposable loopback port."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest


CHECK = Path(__file__).resolve().parents[1] / "deploy" / "check-public.py"
TEAM = "test-team.cloudflareaccess.com"
PATHS = ["/", "/api/v1/games", "/admin", "/api/v1/admin/operations",
         "/api/admin/server/status", "/internal/ready"]
GAMES = ["NIVEL", "ONEPIECE", "POKEMON", "RIFTBOUND", "WEISS", "YUGIOH"]

# Preserve the CLI's production hostname validation and TLS stack. Only the
# default port changes, so parallel tests can run without binding HTTPS port 443.
RUN_CLI = """
import http.client, runpy, sys
def loopback_only(event, args):
    if event == 'socket.getaddrinfo' and args[0] not in ('127.0.0.1', 'localhost'):
        raise AssertionError('unexpected external DNS: ' + repr(args[0]))
    if event == 'socket.connect' and args[1][0] not in ('127.0.0.1', '::1'):
        raise AssertionError('unexpected external connection')
sys.addaudithook(loopback_only)
http.client.HTTPSConnection.default_port = int(sys.argv[1])
del sys.argv[:2]
runpy.run_path(sys.argv[0], run_name='__main__')
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.paths.append(self.path)
        code, headers, body = self.server.routes.get(self.path, (404, {}, b""))
        self.send_response(code)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI needed for temporary test certificates")
class PublicTlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        cls.ca = root / "ca.pem"
        (root / "req.cnf").write_text("[req]\ndistinguished_name=subject\n[subject]\n", encoding="ascii")

        def openssl(*args):
            subprocess.run(["openssl", *args], cwd=root, check=True, capture_output=True)

        new_key = ("-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes")
        openssl("req", "-config", "req.cnf", "-x509", *new_key, "-subj", "/CN=TCG fixture CA", "-days", "1",
                "-keyout", "ca.key", "-out", "ca.pem", "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign")
        openssl("req", "-config", "req.cnf", "-new", *new_key, "-subj", "/CN=TCG route fixture",
                "-keyout", "leaf.key", "-out", "leaf.csr")
        (root / "leaf.ext").write_text("subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n"
                                       "basicConstraints=critical,CA:FALSE\n", encoding="ascii")
        openssl("x509", "-req", "-in", "leaf.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
                "-set_serial", "1", "-days", "1", "-extfile", "leaf.ext", "-out", "leaf.pem")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "leaf.pem", root / "leaf.key")
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.addClassCleanup(cls.server.server_close)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(thread.join)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        self.server.paths = []
        self.server.routes = {
            "/": (200, {}, b'<div id="app"></div>'),
            "/api/v1/games": (200, {}, json.dumps([{"code": code} for code in GAMES]).encode()),
            "/admin": (302, {"Location": f"https://{TEAM}/cdn-cgi/access/login/localhost"}, b""),
            "/api/v1/admin/operations": (401, {}, b""),
            "/api/admin/server/status": (403, {}, b""),
            "/internal/ready": (404, {}, b""),
        }

    def check(self, hostname="127.0.0.1", trust_ca=True):
        env = os.environ.copy()
        if trust_ca:
            env["SSL_CERT_FILE"] = str(self.ca)
        else:
            env.pop("SSL_CERT_FILE", None)
        return subprocess.run([sys.executable, "-I", "-c", RUN_CLI, str(self.server.server_port),
                               str(CHECK), "https://" + hostname, TEAM], env=env,
                              capture_output=True, text=True, timeout=35)

    def test_trusted_chain_and_access_login_without_following_redirect(self):
        result = self.check()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(PATHS, self.server.paths)

    def test_foreign_login_is_rejected_without_following_redirect(self):
        self.server.routes["/admin"] = (302, {"Location": "https://other.invalid/cdn-cgi/access/login/localhost"}, b"")
        result = self.check()
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("expected denial or Cloudflare Access sign-in", result.stderr)
        self.assertEqual(PATHS[:3], self.server.paths)

    def test_untrusted_ca_is_rejected_before_any_http_request(self):
        result = self.check(trust_ca=False)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", result.stderr)
        self.assertEqual([], self.server.paths)

    def test_dns_alias_is_rejected_by_hostname_verification(self):
        result = self.check(hostname="localhost")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("Hostname mismatch", result.stderr)
        self.assertEqual([], self.server.paths)

    def test_challenge_requires_browser_and_other_paths_are_still_checked(self):
        self.server.routes["/"] = (403, {"cf-mitigated": "challenge"}, b"")
        result = self.check()
        self.assertEqual(3, result.returncode, result.stderr)
        self.assertIn("browser verification for: /", result.stderr)
        self.assertEqual(PATHS, self.server.paths)
