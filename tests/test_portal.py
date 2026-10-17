#!/usr/bin/env python3
"""scripts/flowed-portal.mjs — one address for every learner (docs/ENCARREC-PORTAL.md).

Runs the real portal under bun, against fake profile servers (basic auth, one of
them streaming SSE). Every test gets its own portal, so the per-IP failure limit
never leaks between tests. Nothing touches the real ~/.flowed: FLOWED_HOME points
at a temporary directory and FLOWED_ENV_FILE is empty, so the repo .env is ignored.
"""
import base64
import http.client
import http.server
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "scripts" / "flowed-portal.mjs"
BUN = shutil.which("bun") or str(Path.home() / ".bun" / "bin" / "bun")
BUN_OK = Path(BUN).exists()

PW_ANA = "pw-ana-7431"
PW_SHARED = "shared-pw-2291"
PW_OTHER = "other-pw-8820"
PW_BOB = "pw-bob-5517"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeProfile:
    """A profile server: basic auth with login/password, like server/src/http.ts."""

    def __init__(self, tag, login, password):
        self.tag = tag
        expect = "Basic " + base64.b64encode(f"{login}:{password}".encode()).decode()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _ok(self):
                return self.headers.get("Authorization", "") == expect

            def _send(self, status, body, extra=None):
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _deny(self):
                self._send(401, b"Unauthorized", {"WWW-Authenticate": 'Basic realm="FlowEd"'})

            def do_GET(self):
                if not self._ok():
                    return self._deny()
                if self.path == "/api/event":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(b"data: one\n\n")
                    self.wfile.flush()
                    time.sleep(1.2)
                    self.wfile.write(b"data: two\n\n")
                    self.wfile.flush()
                    return
                self._send(200, f"profile={outer.tag} path={self.path}".encode())

            def do_POST(self):
                if not self._ok():
                    return self._deny()
                length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(length)
                self._send(200, b"echo:" + body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def make_profile(home: Path, pid: str, name: str, password: str, level: str, target: str = "English"):
    d = home / pid
    d.mkdir(parents=True)
    lp = {"learner": {"name": name, "current_level": level, "target_language": target}}
    (d / "learner-profile.json").write_text(json.dumps(lp), encoding="utf-8")
    pw = d / ".web-password"
    pw.write_text(password + "\n", encoding="utf-8")
    os.chmod(pw, 0o600)


def request(port, method, path, body=None, cookie=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    h = dict(headers or {})
    if cookie is not None:
        h["Cookie"] = f"flowed_portal={cookie}"
    if isinstance(body, str):
        body = body.encode("utf-8")
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    conn.request(method, path, body=body, headers=h)
    resp = conn.getresponse()
    data = resp.read()
    hdrs = resp.getheaders()
    conn.close()
    return resp.status, hdrs, data


def header_values(hdrs, name):
    return [v for k, v in hdrs if k.lower() == name.lower()]


def cookie_from(hdrs):
    """Value of flowed_portal from Set-Cookie ('' when it is cleared)."""
    for v in header_values(hdrs, "set-cookie"):
        if v.startswith("flowed_portal="):
            return v.split(";", 1)[0][len("flowed_portal="):]
    return None


class PortalCase(unittest.TestCase):
    """Shared fixtures: fake profile servers, profile dirs, one fresh portal per test."""

    @classmethod
    def setUpClass(cls):
        if not BUN_OK:
            raise unittest.SkipTest("bun not installed")
        cls.fakes = {
            "A": FakeProfile("A", "ana", PW_ANA),
            "N1": FakeProfile("N1", "nes", PW_SHARED),
            "N2": FakeProfile("N2", "nes", PW_SHARED),
            "N3": FakeProfile("N3", "nes", PW_OTHER),
        }
        cls.closed_port = free_port()  # nothing listens here: profile is down

    @classmethod
    def tearDownClass(cls):
        for f in cls.fakes.values():
            f.close()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="portal-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        f = self.fakes
        make_profile(self.home, "ana-en", "Ana", PW_ANA, "A2")
        make_profile(self.home, "nes-en", "Nes", PW_SHARED, "A1")
        make_profile(self.home, "nes-math", "Nes", PW_SHARED, "m4")
        make_profile(self.home, "nes-x", "Nes", PW_OTHER, "m2")
        make_profile(self.home, "bob-math", "Bob", PW_BOB, "m2")
        self.webs = " ".join([
            f"ana-en:{f['A'].port}",
            f"nes-en:{f['N1'].port}",
            f"nes-math:{f['N2'].port}",
            f"nes-x:{f['N3'].port}",
            f"bob-math:{self.closed_port}",
        ])
        self.portal_port = free_port()
        self.log_path = self.tmp / "portal.log"
        self.log = open(self.log_path, "w", encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "FLOWED_HOME": str(self.home),
            "FLOWED_PORTAL_PORT": str(self.portal_port),
            "FLOWED_WEBS": self.webs,
            "FLOWED_ENV_FILE": "",
        }
        self.proc = subprocess.Popen([BUN, str(PORTAL)], env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self._wait_healthy()

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait_healthy(self):
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self.fail("portal exited: " + self.log_path.read_text(encoding="utf-8"))
            try:
                status, _, _ = request(self.portal_port, "GET", "/portal/health")
                if status == 200:
                    return
            except OSError:
                pass
            time.sleep(0.1)
        self.fail("portal did not become healthy")

    def login(self, user, password):
        """POST /login and return (status, headers, body)."""
        form = f"user={user}&pass={password}"
        return request(self.portal_port, "POST", "/login", body=form)

    def session_for(self, user, password):
        status, hdrs, _ = self.login(user, password)
        self.assertEqual(status, 303)
        token = cookie_from(hdrs)
        self.assertTrue(token, "login did not set the session cookie")
        return token


@unittest.skipUnless(BUN_OK, "bun not installed")
class EntryAndLoginTest(PortalCase):

    def test_front_page_is_the_login_form_and_never_asks_basic_auth(self):
        status, hdrs, body = request(self.portal_port, "GET", "/")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn('name="user"', text)
        self.assertIn('name="pass"', text)
        self.assertIn("Entra", text)
        self.assertEqual(header_values(hdrs, "www-authenticate"), [])

    def test_api_without_session_is_401_without_basic_prompt(self):
        status, hdrs, _ = request(self.portal_port, "GET", "/api/global/health")
        self.assertEqual(status, 401)
        self.assertEqual(header_values(hdrs, "www-authenticate"), [])

    def test_page_without_session_shows_the_login_form(self):
        status, hdrs, body = request(self.portal_port, "GET", "/app.js")
        self.assertEqual(status, 200)
        self.assertIn('name="pass"', body.decode("utf-8"))
        self.assertEqual(header_values(hdrs, "www-authenticate"), [])

    def test_wrong_password_and_wrong_name_give_the_same_message(self):
        for user, pw in (("ana", "nope"), ("nobody", PW_ANA)):
            status, hdrs, body = self.login(user, pw)
            self.assertEqual(status, 401)
            self.assertIn("Usuari o contrasenya incorrectes", body.decode("utf-8"))
            self.assertIsNone(cookie_from(hdrs))

    def test_one_profile_logs_straight_in_and_proxies_with_its_auth(self):
        status, hdrs, _ = self.login("ana", PW_ANA)
        self.assertEqual(status, 303)
        set_cookie = [v for v in header_values(hdrs, "set-cookie") if v.startswith("flowed_portal=")]
        self.assertEqual(len(set_cookie), 1)
        self.assertIn("HttpOnly", set_cookie[0])
        self.assertIn("SameSite=Lax", set_cookie[0])
        token = cookie_from(hdrs)

        status, hdrs, body = request(self.portal_port, "GET", "/", cookie=token)
        # the fake profile only answers 200 when the portal's Authorization is right
        self.assertEqual(status, 200)
        self.assertEqual(body, b"profile=A path=/")
        self.assertEqual(header_values(hdrs, "www-authenticate"), [])

    def test_health_endpoint(self):
        status, _, body = request(self.portal_port, "GET", "/portal/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.strip(), b"ok")

    def test_secret_file_is_created_with_mode_600(self):
        secret = self.home / ".portal-secret"
        self.assertTrue(secret.exists())
        self.assertEqual(os.stat(secret).st_mode & 0o777, 0o600)


@unittest.skipUnless(BUN_OK, "bun not installed")
class ProfileChoiceTest(PortalCase):

    def test_same_name_and_password_asks_which_profile(self):
        status, hdrs, _ = self.login("nes", PW_SHARED)
        self.assertEqual(status, 303)
        self.assertIn("/switch", header_values(hdrs, "location"))
        pending = cookie_from(hdrs)

        status, _, body = request(self.portal_port, "GET", "/switch", cookie=pending)
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn("Què vols fer?", text)
        self.assertIn("Anglès", text)
        self.assertIn("Matemàtiques", text)
        self.assertIn('value="nes-en"', text)
        self.assertIn('value="nes-math"', text)
        self.assertNotIn('value="nes-x"', text)  # other password: not a candidate

        status, hdrs, _ = request(self.portal_port, "POST", "/choose", body="profile=nes-math", cookie=pending)
        self.assertEqual(status, 303)
        session = cookie_from(hdrs)
        status, _, body = request(self.portal_port, "GET", "/", cookie=session)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"profile=N2 path=/")

    def test_choice_is_limited_to_the_matching_candidates(self):
        pending = cookie_from(self.login("nes", PW_SHARED)[1])
        status, hdrs, _ = request(self.portal_port, "POST", "/choose", body="profile=ana-en", cookie=pending)
        self.assertEqual(status, 303)
        self.assertEqual(header_values(hdrs, "set-cookie"), [])
        # still only pending: the front page keeps offering the choice
        status, hdrs, _ = request(self.portal_port, "GET", "/", cookie=pending)
        self.assertIn("/switch", header_values(hdrs, "location"))

    def test_same_name_different_password_goes_straight_to_the_right_profile(self):
        token = self.session_for("nes", PW_OTHER)
        status, _, body = request(self.portal_port, "GET", "/", cookie=token)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"profile=N3 path=/")

    def test_switch_from_a_session_with_one_profile_goes_home(self):
        token = self.session_for("ana", PW_ANA)
        status, hdrs, _ = request(self.portal_port, "GET", "/switch", cookie=token)
        self.assertEqual(status, 303)
        self.assertIn("/", header_values(hdrs, "location"))

    def test_switch_without_session_goes_to_login(self):
        status, hdrs, _ = request(self.portal_port, "GET", "/switch")
        self.assertEqual(status, 303)
        self.assertIn("/", header_values(hdrs, "location"))


@unittest.skipUnless(BUN_OK, "bun not installed")
class SessionTest(PortalCase):

    def test_tampered_cookie_goes_back_to_login(self):
        token = self.session_for("ana", PW_ANA)
        last = token[-1]
        forged = token[:-1] + ("A" if last != "A" else "B")
        status, _, body = request(self.portal_port, "GET", "/", cookie=forged)
        self.assertEqual(status, 200)
        self.assertIn('name="pass"', body.decode("utf-8"))
        self.assertNotIn(b"profile=A", body)

    def test_a_made_up_cookie_is_not_a_session(self):
        status, _, body = request(self.portal_port, "GET", "/", cookie="eyJwIjoiYW5hLWVuIn0.nope")
        self.assertEqual(status, 200)
        self.assertIn('name="pass"', body.decode("utf-8"))

    def test_logout_clears_the_cookie(self):
        token = self.session_for("ana", PW_ANA)
        status, hdrs, _ = request(self.portal_port, "GET", "/logout", cookie=token)
        self.assertEqual(status, 303)
        set_cookie = [v for v in header_values(hdrs, "set-cookie") if v.startswith("flowed_portal=")]
        self.assertTrue(set_cookie and "Max-Age=0" in set_cookie[0])
        status, _, body = request(self.portal_port, "GET", "/")  # browser dropped the cookie
        self.assertIn('name="pass"', body.decode("utf-8"))

    def test_session_is_bound_to_the_profile_it_was_given(self):
        ana = self.session_for("ana", PW_ANA)
        bob_status, _, _ = self.login("bob", PW_BOB)
        self.assertEqual(bob_status, 303)
        status, _, body = request(self.portal_port, "GET", "/", cookie=ana)
        self.assertEqual(body, b"profile=A path=/")


@unittest.skipUnless(BUN_OK, "bun not installed")
class ProxyTest(PortalCase):

    def test_post_body_is_forwarded(self):
        token = self.session_for("ana", PW_ANA)
        status, hdrs, body = request(self.portal_port, "POST", "/api/echo", body="hello-body", cookie=token)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"echo:hello-body")
        self.assertEqual(header_values(hdrs, "www-authenticate"), [])

    def test_sse_streams_without_buffering(self):
        token = self.session_for("ana", PW_ANA)
        conn = http.client.HTTPConnection("127.0.0.1", self.portal_port, timeout=15)
        conn.request("GET", "/api/event", headers={"Cookie": f"flowed_portal={token}"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        arrivals = {}
        started = time.monotonic()
        while True:
            chunk = resp.read1(64)
            if not chunk:
                break
            now = time.monotonic() - started
            if b"one" in chunk:
                arrivals.setdefault("one", now)
            if b"two" in chunk:
                arrivals.setdefault("two", now)
        conn.close()
        self.assertIn("one", arrivals)
        self.assertIn("two", arrivals)
        self.assertGreaterEqual(arrivals["two"] - arrivals["one"], 0.8,
                                "the two SSE events arrived together: the stream is buffered")

    def test_profile_that_is_down_shows_the_unavailable_page(self):
        token = self.session_for("bob", PW_BOB)
        status, hdrs, body = request(self.portal_port, "GET", "/", cookie=token)
        self.assertEqual(status, 503)
        text = body.decode("utf-8")
        self.assertIn("Ara no està disponible", text)
        self.assertIn("/logout", text)
        self.assertEqual(header_values(hdrs, "www-authenticate"), [])

    def test_env_file_supplies_webs_and_port(self):
        env_file = self.tmp / "portal.env"
        port = free_port()
        env_file.write_text(
            f'FLOWED_PORTAL_PORT={port}\nFLOWED_WEBS="ana-en:{self.fakes["A"].port}"  # comentari\n',
            encoding="utf-8",
        )
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.log.close()
        self.log = open(self.log_path, "w", encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "FLOWED_HOME": str(self.home),
            "FLOWED_ENV_FILE": str(env_file),
        }
        self.proc = subprocess.Popen([BUN, str(PORTAL)], env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self.portal_port = port
        self._wait_healthy()
        token = self.session_for("ana", PW_ANA)
        status, _, body = request(self.portal_port, "GET", "/", cookie=token)
        self.assertEqual(body, b"profile=A path=/")


@unittest.skipUnless(BUN_OK, "bun not installed")
class RateLimitAndSecrecyTest(PortalCase):

    def test_five_failures_in_five_minutes_lock_the_ip(self):
        for _ in range(5):
            status, _, _ = self.login("ana", "wrong")
            self.assertEqual(status, 401)
        status, hdrs, body = self.login("ana", PW_ANA)  # right password, still locked
        self.assertEqual(status, 429)
        self.assertTrue(header_values(hdrs, "retry-after"))
        self.assertIn("Massa intents", body.decode("utf-8"))
        self.assertIsNone(cookie_from(hdrs))

    def test_passwords_never_reach_the_log(self):
        self.login("ana", "wrong-guess-3311")
        self.login("ana", PW_ANA)
        self.login("nes", PW_SHARED)
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.log.close()
        text = self.log_path.read_text(encoding="utf-8")
        for secret in (PW_ANA, PW_SHARED, PW_OTHER, PW_BOB, "wrong-guess-3311"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
