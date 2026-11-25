import importlib.util
import json
from pathlib import Path
import unittest


src = Path(__file__).resolve().parents[1] / "deploy" / "check-public.py"
spec = importlib.util.spec_from_file_location("public_routes", src)
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


class PublicRouteTest(unittest.TestCase):
    def setUp(self):
        self.site = "https://cards.example.org"
        self.team = "cards-team.cloudflareaccess.com"
        self.responses = {
            "/": (200, None, b'<div id="app"></div>'),
            "/api/v1/games": (200, None, json.dumps([{"code": code} for code in public.GAMES])),
            "/admin": (302, "https://" + self.team + "/cdn-cgi/access/login/cards.example.org", b""),
            "/api/v1/admin/operations": (403, None, b""),
            "/internal/ready": (403, None, b""),
        }

    def check(self):
        public.check_routes(self.site, self.team, self.responses.__getitem__)

    def test_catalog_public_while_admin_and_readiness_require_protection(self):
        self.check()
        for path in ("/admin", "/api/v1/admin/operations", "/internal/ready"):
            with self.subTest(path=path):
                original = self.responses[path]
                self.responses[path] = (200, None, b"")
                with self.assertRaises(public.RouteError):
                    self.check()
                self.responses[path] = original

    def test_catalog_redirect_or_wrong_app_does_not_prove_public_access(self):
        for response in ((302, "/login", b""), (200, None, b"[]"), (200, None, b"<html>")):
            self.responses["/api/v1/games"] = response
            with self.assertRaises(public.RouteError):
                self.check()

    def test_public_homepage_cannot_require_sign_in_or_be_an_edge_placeholder(self):
        for response in ((302, "/login", b""), (200, None, b"<title>Welcome</title>")):
            self.responses["/"] = response
            with self.assertRaises(public.RouteError):
                self.check()

    def test_admin_redirect_must_lead_to_configured_access_login(self):
        for location in ("/login", "https://example.net/cdn-cgi/access/login/cards.example.org"):
            self.responses["/admin"] = (302, location, b"")
            with self.assertRaises(public.RouteError):
                self.check()

    def test_edge_not_ready_can_retry(self):
        self.responses["/api/v1/games"] = (503, None, b"")
        with self.assertRaises(ConnectionError):
            self.check()
