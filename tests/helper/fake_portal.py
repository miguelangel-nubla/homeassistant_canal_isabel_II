"""A stand-in for the virtual office and for Home Assistant, for e2e.py.

One small web server plays both parts. As the portal it has a login form
with the same fields and the same behaviour as the real one (a profile to
choose, a button that asks an invisible captcha before sending the form)
and a consumption page that needs a session. As Home Assistant it records
the service calls the helper makes.
"""
import json
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DOCUMENT = "X1234567L"
PASSWORD = "correct horse; battery 'staple'"
HA_TOKEN = "test-token"
FIELD = "_com_vass_cyii_ovir_login_module_"

LOGIN_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Acceso</title>
<style>.d-none { display: none; } .d-block { display: block; }</style>
</head><body>
%(error)s
<div id="login-form">
<form id="_com_vass_cyii_ovir_login_module_loginForm" action="/web/ovir/login" method="post">
  <input type="hidden" value="" id="tipoUsuario" name="_com_vass_cyii_ovir_login_module_tipoUsuario">
  <input id="radioParticularLoginDesktop" name="tipoUsuarioDesktop" type="radio" value="PARTICULAR">
  <input id="radioEmpresaLoginDesktop" name="tipoUsuarioDesktop" type="radio" value="GES_EMPRESAS">
  <select id="tipoDocumento" name="_com_vass_cyii_ovir_login_module_tipoDocumento">
    <option value="NIF">NIF</option><option value="NIE">NIE</option>
  </select>
  <input id="numeroDocumento" name="_com_vass_cyii_ovir_login_module_numeroDocumento" type="text" value="">
  <p class="invalid d-none" id="noNumDocLogin">Introduzca un número de documento correcto.</p>
  <input id="passwordFieldHidden" name="_com_vass_cyii_ovir_login_module_password" type="password">
  <div id="recaptcha-login"></div>
  <button id="btLogin" type="button">Entrar</button>
</form>
</div>
<!-- The real page carries hidden messages like this one. -->
<div id="bannerSessionExpired" class="d-none"><div role="alert">Tu sesión ha caducado</div></div>
<script>
  for (const radio of document.querySelectorAll('input[type=radio]')) {
    radio.addEventListener('click', () => { document.getElementById('tipoUsuario').value = radio.value; });
  }
  function onSubmit() { document.getElementById('_com_vass_cyii_ovir_login_module_loginForm').submit(); }
  function renderRecaptchaLogin() {
    recaptchaLogin = grecaptcha.enterprise.render('recaptcha-login', {callback: onSubmit, size: 'invisible'});
  }
  document.getElementById('btLogin').onclick = () => {
    const number = document.getElementById('numeroDocumento').value;
    const type = document.getElementById('tipoDocumento').value;
    const fits = (type === 'NIE' ? /^[XYZ][0-9]{7}[A-Z]$/ : /^[0-9]{8}[A-Z]$/).test(number);
    document.getElementById('noNumDocLogin').className = fits ? 'invalid d-none' : 'invalid d-block';
    const filled = ['tipoUsuario', 'passwordFieldHidden'].every(id => document.getElementById(id).value);
    if (fits && filled) grecaptcha.enterprise.execute(recaptchaLogin);
  };
</script>
<script src="/recaptcha/enterprise.js?onload=renderRecaptchaLogin" async defer></script>
</body></html>
"""

# What Google's script does, as far as the page can tell: render() keeps the
# callback and execute() calls it a moment later, or shows a challenge.
CAPTCHA_SCRIPT = """
window.grecaptcha = {enterprise: {
  render(id, options) { this.callback = options.callback; return 0; },
  execute() {
    if (%(challenge)s) {
      const frame = document.createElement('iframe');
      frame.src = '/recaptcha/enterprise/bframe';
      frame.style.cssText = 'width: 300px; height: 400px';
      document.body.appendChild(frame);
    } else {
      setTimeout(this.callback, 300);
    }
  },
  reset() {},
}};
window[new URL(document.currentScript.src).searchParams.get('onload')]();
"""

CONSUMPTION_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Consumo</title></head><body>
<select id="selectPeriodicidad"><option>Horaria</option></select>
<a href="/export-csv?fileFormat=CSV">CSV</a>
</body></html>
"""


class State:
    """What the tests set up and what they look at afterwards."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.sessions = set()   # sessions that are logged in
            self.issued = 0
            self.login_posts = []   # the forms received, as dicts
            self.ha_calls = []      # (service, data)
            self.challenge = False  # the captcha asks for a person

    def new_cookie(self, prefix: str) -> str:
        self.issued += 1
        return f"{prefix}-{self.issued}"

    def calls(self, service: str) -> list:
        with self.lock:
            return [data for name, data in self.ha_calls if name == service]


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        def _send(self, status: int, body: str = "", content_type: str = "text/html", headers=()) -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, location: str, cookie: str = "") -> None:
            headers = [("Location", location)]
            if cookie:
                headers.append(("Set-Cookie", f"JSESSIONID={cookie}; Path=/; HttpOnly"))
            self._send(302, headers=headers)

        def _cookie(self) -> str:
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get("JSESSIONID")
            return morsel.value if morsel else ""

        def _body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length", "0")))

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/group/ovir/consumo":
                with state.lock:
                    logged_in = self._cookie() in state.sessions
                if logged_in:
                    self._send(200, CONSUMPTION_PAGE)
                else:
                    self._redirect("/login?redirect=%2Fgroup%2Fovir%2Fconsumo")
            elif url.path == "/login":
                error = ""
                if "error" in parse_qs(url.query):
                    error = '<div class="alert alert-danger" role="alert">Usuario o contraseña incorrectos</div>'
                headers = []
                if not self._cookie():
                    with state.lock:
                        headers.append(("Set-Cookie", f"JSESSIONID={state.new_cookie('anon')}; Path=/; HttpOnly"))
                self._send(200, LOGIN_PAGE % {"error": error}, headers=headers)
            elif url.path == "/recaptcha/enterprise.js":
                with state.lock:
                    challenge = "true" if state.challenge else "false"
                self._send(200, CAPTCHA_SCRIPT % {"challenge": challenge}, "application/javascript")
            elif url.path == "/recaptcha/enterprise/bframe":
                self._send(200, "<p>Selecciona todas las imágenes con semáforos</p>")
            else:
                self._send(404, "not found")

        def do_POST(self) -> None:
            url = urlparse(self.path)
            body = self._body()
            if url.path == "/web/ovir/login":
                form = {key.removeprefix(FIELD): values[0] for key, values in parse_qs(body.decode()).items()}
                accepted = (
                    form.get("tipoUsuario") == "PARTICULAR"
                    and form.get("tipoDocumento") == "NIE"
                    and form.get("numeroDocumento") == DOCUMENT
                    and form.get("password") == PASSWORD
                )
                with state.lock:
                    state.login_posts.append(form)
                    if accepted:
                        cookie = state.new_cookie("session")
                        state.sessions.add(cookie)
                if accepted:
                    self._redirect("/group/ovir/consumo", cookie)
                else:
                    self._redirect("/login?error=1")
            elif url.path.startswith("/api/services/"):
                if self.headers.get("Authorization") != f"Bearer {HA_TOKEN}":
                    self._send(401, "unauthorized")
                    return
                service = url.path.removeprefix("/api/services/")
                data = json.loads(body or b"{}")
                with state.lock:
                    state.ha_calls.append((service, data))
                    refused = (
                        service == "canal_de_isabel_ii/set_session"
                        and data.get("jsessionid") not in state.sessions
                    )
                if refused:
                    self._send(400, '{"message": "session rejected"}', "application/json")
                else:
                    self._send(200, "[]", "application/json")
            else:
                self._send(404, "not found")

    return Handler


def serve(state: State) -> ThreadingHTTPServer:
    """Start the server on a free port, in the background."""
    server = ThreadingHTTPServer(("0.0.0.0", 0), make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
