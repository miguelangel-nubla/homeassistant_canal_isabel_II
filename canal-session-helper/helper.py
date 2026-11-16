"""Hold a portal session in a real browser and pass it to Home Assistant.

The browser of this container logs in to the Canal de Isabel II virtual
office, either by itself with the credentials it was given (CANAL_DOCUMENT
and CANAL_PASSWORD) or by the hand of a person through the remote view.
This script then reads the session cookie, hands it to the integration with
the canal_de_isabel_ii.set_session service, and keeps checking the session.
When the portal ends the session it logs in again. Only when that is not
possible does it ask for a login through a Home Assistant notification.

The login form runs an invisible reCAPTCHA, which is why the login happens
in a real browser. Nothing here answers or avoids it: if it asks for a
challenge, or the portal refuses the login, a person is asked to step in.
The portal's cookie dialog is answered with "allow all".
"""
import glob
import hashlib
import json
import logging
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request

import websocket

# PORTAL_URL exists for the tests, which run a fake portal.
BASE_URL = os.environ.get("PORTAL_URL", "https://oficinavirtual.canaldeisabelsegunda.es").rstrip("/")
CONSUMPTION_URL = f"{BASE_URL}/group/ovir/consumo"
CDP = "http://127.0.0.1:9222"
PROFILE_DIR = "/data/profile"
# The portal's cookie is a session cookie, which Chromium forgets when it
# closes. A copy is kept here so a restart of the container or the browser
# does not ask for a new login while the portal still accepts the session.
SESSION_FILE = "/data/session"
# What the automatic login remembers between restarts (see AutoLogin).
LOGIN_STATE_FILE = "/data/login_state"
RETRY_INTERVAL = 60
NOTIFICATION_ID = "canal_de_isabel_ii_login_needed"

HA_URL = os.environ["HA_URL"].rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
if not HA_TOKEN:
    with open(os.environ["HA_TOKEN_FILE"], encoding="utf-8") as _token_file:
        HA_TOKEN = _token_file.read().strip()
HA_ENTRY_ID = os.environ.get("HA_ENTRY_ID", "")
HA_VERIFY_SSL = os.environ.get("HA_VERIFY_SSL", "true").lower() != "false"
HELPER_URL = os.environ.get("HELPER_URL", "")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))
SCREEN_SIZE = os.environ.get("SCREEN_SIZE", "1280x800").replace("x", ",")
LOGIN_POLL = 5


def _secret(name: str) -> str:
    """A secret given directly (NAME) or as the first line of a file (NAME_FILE)."""
    value = os.environ.get(name, "")
    path = os.environ.get(f"{name}_FILE", "")
    if not value and path:
        with open(path, encoding="utf-8") as secret_file:
            value = secret_file.readline().rstrip("\r\n")
    return value


# Credentials for the automatic login. Without them a person logs in.
LOGIN_DOCUMENT = os.environ.get("CANAL_DOCUMENT", "").strip().upper()
LOGIN_PASSWORD = _secret("CANAL_PASSWORD")
LOGIN_PROFILE = os.environ.get("CANAL_PROFILE", "").strip().lower() or "particular"
# The profile to choose on the login form, by the id of its radio button.
PROFILES = {
    "particular": "radioParticularLoginDesktop",
    "empresa": "radioEmpresaLoginDesktop",
    "administrador": "radioAdministradorFincasLoginDesktop",
    "entidad_publica": "radioEntidadesPublicasLoginDesktop",
}

# How long a login may take from the click to the logged-in page.
LOGIN_TIMEOUT = int(os.environ.get("LOGIN_TIMEOUT", "90"))
# A login the portal refused is tried again after these waits and then no
# more: repeating a wrong password could get the account locked.
REFUSED_DELAYS = (3600, 6 * 3600)
# A login that could not be completed (the portal is down, the page did not
# load, a captcha challenge nobody answered) is tried again, forever.
FAILED_DELAYS = (300, 900, 1800, 3600)

LOGIN_OK = "ok"
LOGIN_REFUSED = "refused"      # the portal answered the login with the form again
LOGIN_CHALLENGE = "challenge"  # the captcha wants a person
LOGIN_FAILED = "failed"        # no answer that could be understood

LOGIN_FORM_JS = (
    "!!document.querySelector('#btLogin') && !!document.querySelector('#numeroDocumento')"
    " && !!document.querySelector('#passwordFieldHidden')"
)
# True when the form holds something this script did not write there.
TYPED_BY_PERSON_JS = (
    "!window.__helperLogin && ['numeroDocumento', 'passwordFieldHidden']"
    ".some(id => (document.getElementById(id) || {}).value)"
)
CAPTCHA_READY_JS = (
    "typeof grecaptcha !== 'undefined' && !!grecaptcha.enterprise"
    " && typeof recaptchaLogin !== 'undefined'"
)
# reCAPTCHA shows its challenge in this frame, hidden until it is needed.
CAPTCHA_CHALLENGE_JS = """
[...document.querySelectorAll('iframe[src*="recaptcha"][src*="bframe"]')].some(frame => {
    const box = frame.getBoundingClientRect();
    let visible = box.width > 0 && box.height > 0;
    for (let node = frame; node && visible; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (style.visibility === 'hidden' || style.display === 'none') visible = false;
    }
    return visible;
})
"""
# The portal asks about cookies with a Cookiebot dialog, which stays on top
# of the page until it is answered. The helper answers "allow all": with
# fewer cookies parts of the portal may not work.
COOKIES_UNANSWERED_JS = (
    "typeof Cookiebot !== 'undefined' && !Cookiebot.consented && !Cookiebot.declined"
)
COOKIES_ALLOW_ALL_ID = "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"
COOKIES_BUTTON_JS = f"!!(document.getElementById('{COOKIES_ALLOW_ALL_ID}') || {{}}).offsetParent"

# What is written in the elements that match a selector and are on screen
# (the page also carries hidden messages), for the log and the notification.
_SHOWN_TEXT_JS = """
[...document.querySelectorAll('%s')].filter(node => node.getClientRects().length)
    .map(node => node.innerText.replace(/\\s+/g, ' ').trim()).filter(Boolean).join(' / ').slice(0, 200)
"""
# The form's own complaints, before anything is sent.
FORM_COMPLAINTS_JS = _SHOWN_TEXT_JS % "#login-form label.error, #login-form .invalid.d-block"
# The portal's answer to a login it did not accept.
PORTAL_ERRORS_JS = _SHOWN_TEXT_JS % (
    '[role="alert"], .alert-danger, .alert-error, .portlet-msg-error, #login-form .invalid.d-block'
)

# True once the page is a logged-in consumption page.
LOGGED_IN_JS = (
    "location.pathname.startsWith('/group/') && "
    "!!document.querySelector('a[href*=\"export-csv\"], #selectPeriodicidad')"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("helper")


# --- Home Assistant -------------------------------------------------------

def addon_ingress_url() -> str:
    """As an add-on, the path that opens this add-on's page in Home Assistant."""
    request = urllib.request.Request(
        "http://supervisor/addons/self/info",
        headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return f"/hassio/ingress/{json.load(response)['data']['slug']}"
    except (OSError, KeyError, ValueError) as err:
        log.warning("Could not ask the Supervisor for the add-on address: %s", err)
        return ""


def call_ha(service: str, data: dict) -> bool:
    """Call a Home Assistant service. Returns True on success."""
    request = urllib.request.Request(
        f"{HA_URL}/api/services/{service}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    context = None
    if HA_URL.startswith("https") and not HA_VERIFY_SSL:
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=90, context=context):
            return True
    except urllib.error.HTTPError as err:
        log.warning("Home Assistant refused %s: HTTP %s %s", service, err.code, err.read()[:300])
    except OSError as err:
        log.warning("Home Assistant not reachable for %s: %s", service, err)
    return False


def send_session(jsessionid: str) -> bool:
    data = {"jsessionid": jsessionid}
    if HA_ENTRY_ID:
        data["entry_id"] = HA_ENTRY_ID
    return call_ha("canal_de_isabel_ii/set_session", data)


def notify_login_needed(reason: str = "") -> bool:
    """Ask for a login by hand. reason says why the automatic one did not do it."""
    # Shown to the person in Home Assistant, whose users are Spanish speakers.
    where = f"[Abre el navegador del ayudante]({HELPER_URL})" if HELPER_URL else "Abre el navegador del ayudante"
    message = f"No hay ninguna sesión activa en la oficina virtual. {where} e inicia sesión."
    if reason:
        message = f"{reason}\n\n{message}"
    return call_ha(
        "persistent_notification/create",
        {
            "notification_id": NOTIFICATION_ID,
            "title": "Canal de Isabel II: hay que iniciar sesión",
            "message": message,
        },
    )


def dismiss_notification() -> None:
    call_ha("persistent_notification/dismiss", {"notification_id": NOTIFICATION_ID})


# --- Browser --------------------------------------------------------------

def start_browser() -> subprocess.Popen:
    """Start Chromium on the virtual screen with a local control port."""
    # A lock left by a previous container would stop Chromium from starting.
    for lock in glob.glob(f"{PROFILE_DIR}/Singleton*"):
        os.remove(lock)
    process = subprocess.Popen(
        [
            "chromium",
            f"--user-data-dir={PROFILE_DIR}",
            "--remote-debugging-port=9222",
            # Containers rarely allow Chromium's own sandbox. This browser is
            # only meant for the Canal de Isabel II portal.
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--lang=es-ES",
            "--window-position=0,0",
            f"--window-size={SCREEN_SIZE}",
            CONSUMPTION_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{CDP}/json/version", timeout=2).close()
            return process
        except OSError:
            time.sleep(1)
    process.kill()
    raise RuntimeError("Chromium did not start")


class Tab:
    """The first browser tab, driven over Chromium's local control port."""

    def __init__(self) -> None:
        with urllib.request.urlopen(f"{CDP}/json/list", timeout=5) as response:
            pages = [t for t in json.load(response) if t.get("type") == "page"]
        if not pages:
            request = urllib.request.Request(f"{CDP}/json/new?{CONSUMPTION_URL}", method="PUT")
            with urllib.request.urlopen(request, timeout=5) as response:
                pages = [json.load(response)]
        self._ws = websocket.create_connection(
            pages[0]["webSocketDebuggerUrl"], timeout=30, suppress_origin=True
        )
        self._next_id = 0

    def close(self) -> None:
        self._ws.close()

    def _call(self, method: str, params: dict = None) -> dict:
        self._next_id += 1
        self._ws.send(json.dumps({"id": self._next_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self._ws.recv())
            if message.get("id") == self._next_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def evaluate(self, expression: str):
        result = self._call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result["result"].get("value")

    def url(self) -> str:
        return self.evaluate("location.href") or ""

    def open(self, url: str) -> None:
        """Navigate and wait for the page to finish loading."""
        self._call("Page.navigate", {"url": url})
        time.sleep(2)
        for _ in range(60):
            try:
                if self.evaluate("document.readyState") == "complete":
                    return
            except RuntimeError:
                pass  # page is mid-navigation
            time.sleep(1)

    def logged_in(self) -> bool:
        return bool(self.evaluate(LOGGED_IN_JS))

    def wait_for(self, expression: str, seconds: int) -> bool:
        """Wait until the expression is true. False if it never was."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                if self.evaluate(expression):
                    return True
            except RuntimeError:
                pass  # page is mid-navigation
            if time.monotonic() >= deadline:
                return False
            time.sleep(1)

    def allow_cookies(self, wait: int = 0) -> None:
        """Answer the cookie dialog, if the page is asking, with "allow all"."""
        try:
            if not self.evaluate(COOKIES_UNANSWERED_JS) or not self.wait_for(COOKIES_BUTTON_JS, wait):
                return
            self.evaluate(f"document.getElementById('{COOKIES_ALLOW_ALL_ID}').click()")
            self.wait_for(f"!({COOKIES_BUTTON_JS})", 5)
            log.info("Cookie dialog answered: all cookies allowed.")
        except RuntimeError:
            pass  # page is mid-navigation; the dialog comes back on the next page

    def type_into(self, element_id: str, text: str) -> bool:
        """Replace the content of a field, as typing does. True if it took it.

        The text travels as keyboard input and never as part of a script, so
        it cannot end up in an error message or a log.
        """
        self.evaluate(
            f"(() => {{ const field = document.getElementById('{element_id}');"
            " field.focus(); field.select(); })()"
        )
        self._call("Input.insertText", {"text": text})
        length = self.evaluate(f"document.getElementById('{element_id}').value.length")
        return length == len(text)

    def click(self, element_id: str) -> None:
        """Click an element: with the mouse if it can be reached, else directly.

        Something may lie on top of the element. The portal's cookie dialog
        covers the login button in a browser that has never answered it.
        """
        box = self.evaluate(
            f"(() => {{ const node = document.getElementById('{element_id}');"
            " node.scrollIntoView({block: 'center'});"
            " const box = node.getBoundingClientRect();"
            " const x = box.left + box.width / 2, y = box.top + box.height / 2;"
            " return {x, y, reachable: node.contains(document.elementFromPoint(x, y))}; })()"
        )
        if not box["reachable"]:
            self.evaluate(f"document.getElementById('{element_id}').click()")
            return
        for event in ("mousePressed", "mouseReleased"):
            self._call(
                "Input.dispatchMouseEvent",
                {"type": event, "x": box["x"], "y": box["y"], "button": "left", "clickCount": 1},
            )

    def session_cookie(self) -> str:
        cookies = self._call("Network.getCookies", {"urls": [BASE_URL]})["cookies"]
        return next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), "")

    def set_session_cookie(self, value: str) -> None:
        self._call(
            "Network.setCookie",
            {
                "name": "JSESSIONID",
                "value": value,
                "url": BASE_URL,
                "path": "/",
                "secure": BASE_URL.startswith("https"),
                "httpOnly": True,
            },
        )


def saved_session() -> str:
    try:
        with open(SESSION_FILE, encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


def save_session(cookie: str) -> None:
    """Keep (or with an empty value, forget) the session for the next start."""
    try:
        if not cookie:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            return
        descriptor = os.open(SESSION_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(cookie)
    except OSError as err:
        log.warning("Could not update %s: %s", SESSION_FILE, err)


class AutoLogin:
    """When the automatic login may be tried, remembered across restarts.

    A restart must not be a way to try a refused password again, so the
    count of refusals and the time of the next try are kept in /data. They
    are forgotten when the credentials change or a login succeeds, by this
    script or by a person.
    """

    def __init__(self) -> None:
        # Tells one set of credentials from another without keeping them.
        self._key = hashlib.sha256(
            "\0".join((LOGIN_PROFILE, LOGIN_DOCUMENT, LOGIN_PASSWORD)).encode()
        ).hexdigest()
        self.refusals = 0
        self.failures = 0
        self.next_try = 0.0  # epoch seconds; None when no more tries are due
        try:
            with open(LOGIN_STATE_FILE, encoding="utf-8") as file:
                state = json.load(file)
            if state["key"] == self._key:
                self.refusals = int(state["refusals"])
                self.failures = int(state["failures"])
                self.next_try = state["next_try"]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _save(self) -> None:
        state = {
            "key": self._key,
            "refusals": self.refusals,
            "failures": self.failures,
            "next_try": self.next_try,
        }
        try:
            descriptor = os.open(LOGIN_STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(state, file)
        except OSError as err:
            log.warning("Could not update %s: %s", LOGIN_STATE_FILE, err)

    def due(self) -> bool:
        return self.next_try is not None and time.time() >= self.next_try

    def record(self, outcome: str) -> None:
        """Note how a try ended and decide when the next one is."""
        if outcome == LOGIN_OK:
            self.reset()
            return
        if outcome == LOGIN_REFUSED:
            self.refusals += 1
            if self.refusals > len(REFUSED_DELAYS):
                self.next_try = None
            else:
                self.next_try = time.time() + REFUSED_DELAYS[self.refusals - 1]
        else:
            self.failures += 1
            delay = FAILED_DELAYS[min(self.failures, len(FAILED_DELAYS)) - 1]
            if outcome == LOGIN_CHALLENGE:
                # Leave the challenge on screen for a person to answer.
                delay = FAILED_DELAYS[-1]
            self.next_try = time.time() + delay
        self._save()

    def reset(self) -> None:
        if self.refusals or self.failures or self.next_try:
            self.refusals = self.failures = 0
            self.next_try = 0.0
            self._save()

    def when(self) -> str:
        """The next try, in the words of the notification."""
        if self.next_try is None:
            return (
                "No se volverá a intentar hasta que inicies sesión a mano "
                "o cambies las credenciales del ayudante."
            )
        return time.strftime("Se volverá a intentar a las %H:%M.", time.localtime(self.next_try))


def attempt_login(tab: Tab) -> tuple:
    """Fill in the login form and send it. Returns (outcome, detail)."""
    tab.open(CONSUMPTION_URL)  # without a session the portal answers with the login form
    if tab.logged_in():
        return LOGIN_OK, ""
    if not tab.wait_for(LOGIN_FORM_JS, 20):
        return LOGIN_FAILED, "the login form did not appear"
    # The button does nothing until the captcha script has loaded.
    if not tab.wait_for(CAPTCHA_READY_JS, 30):
        return LOGIN_FAILED, "the captcha of the login form did not load"
    tab.allow_cookies(wait=10)

    document_type = "NIE" if re.match(r"[XYZ]\d", LOGIN_DOCUMENT) else "NIF"
    tab.evaluate(
        "(() => { window.__helperLogin = true;"
        f" document.getElementById('{PROFILES[LOGIN_PROFILE]}').click();"
        " const type = document.getElementById('tipoDocumento');"
        f" if (type) {{ type.value = '{document_type}';"
        " type.dispatchEvent(new Event('change', {bubbles: true})); } })()"
    )
    if not tab.type_into("numeroDocumento", LOGIN_DOCUMENT) or not tab.type_into(
        "passwordFieldHidden", LOGIN_PASSWORD
    ):
        return LOGIN_FAILED, "the login form did not take the credentials"
    tab.click("btLogin")

    # The page that answers the login no longer carries the mark set above.
    deadline = time.monotonic() + LOGIN_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            if tab.evaluate("document.readyState") != "complete":
                continue
            if tab.evaluate("window.__helperLogin"):
                # Still on the form: it is waiting for the captcha, or it
                # found something wrong before sending anything.
                if tab.evaluate(CAPTCHA_CHALLENGE_JS):
                    return LOGIN_CHALLENGE, ""
                complaint = tab.evaluate(FORM_COMPLAINTS_JS)
                if complaint:
                    return LOGIN_REFUSED, complaint
                continue
            if tab.evaluate("location.pathname.startsWith('/group/')"):
                if not tab.logged_in():
                    tab.open(CONSUMPTION_URL)
                if tab.logged_in():
                    return LOGIN_OK, ""
                return LOGIN_FAILED, "logged in, but the consumption page did not open"
            if tab.evaluate(LOGIN_FORM_JS):
                return LOGIN_REFUSED, tab.evaluate(PORTAL_ERRORS_JS) or ""
        except RuntimeError:
            pass  # page is mid-navigation
    return LOGIN_FAILED, "the portal did not answer the login"


def automatic_login(tab: Tab, auto: AutoLogin) -> str:
    """Try to log in. Returns "" on success, else why not, for the person."""
    log.info("Logging in with the configured credentials.")
    try:
        outcome, detail = attempt_login(tab)
    except (RuntimeError, TypeError, KeyError) as err:
        outcome, detail = LOGIN_FAILED, f"the browser did not follow: {err}"
    auto.record(outcome)
    if outcome == LOGIN_OK:
        log.info("Logged in.")
        return ""
    if outcome == LOGIN_REFUSED:
        log.warning("The portal refused the login%s.", f": {detail}" if detail else "")
        reason = "El portal ha rechazado el inicio de sesión automático"
        reason += f" («{detail}»)." if detail else ". Comprueba el documento, la contraseña y el perfil."
    elif outcome == LOGIN_CHALLENGE:
        log.warning("The captcha of the login form asks for a person.")
        reason = "El portal pide resolver una comprobación (captcha) para iniciar sesión."
    else:
        log.warning("The login could not be completed: %s.", detail)
        reason = "El inicio de sesión automático no se ha podido completar."
    if auto.next_try is None:
        log.warning("No more automatic logins until the credentials change or a person logs in.")
    else:
        log.info("Next automatic login at %s.", time.strftime("%H:%M", time.localtime(auto.next_try)))
    return f"{reason} {auto.when()}"


def wait_for_login(tab: Tab, auto: AutoLogin = None) -> None:
    """Get the browser logged in, by itself or by waiting for a person.

    With credentials, the login is tried whenever it is due. A person is
    asked only once a try has failed, and can log in at any moment. While
    waiting, the page is only reloaded when it sits on a portal page that
    should be the consumption page, or on no portal page at all (a failed
    load), and then at most once a minute.
    """
    reason = ""
    if auto and not auto.due():
        reason = f"El inicio de sesión automático está en pausa. {auto.when()}"
    # Nobody is asked while the automatic login is about to try.
    ask = not auto or bool(reason)
    notified = False
    last_try = float("-inf")
    last_open = time.monotonic()
    while True:
        # Not while a person is filling in the form.
        if auto and auto.due() and not tab.evaluate(TYPED_BY_PERSON_JS):
            reason = automatic_login(tab, auto)
            if not reason:
                return
            ask, notified = True, False
            last_try = float("-inf")
            last_open = time.monotonic()
        now = time.monotonic()
        if ask and not notified and now - last_try >= RETRY_INTERVAL:
            # Asked again every minute while Home Assistant is not reachable.
            notified = notify_login_needed(reason)
            last_try = now
        time.sleep(LOGIN_POLL)
        now = time.monotonic()
        url = tab.url()
        inside = url.startswith(f"{BASE_URL}/group/")
        if (inside or not url.startswith(BASE_URL)) and now - last_open >= RETRY_INTERVAL:
            tab.open(CONSUMPTION_URL)
            last_open = time.monotonic()
        if inside and tab.logged_in():
            if auto:
                auto.reset()  # a person logged in: the refusals are history
            return


def run(browser: subprocess.Popen) -> None:
    tab = Tab()
    auto = AutoLogin() if LOGIN_DOCUMENT and LOGIN_PASSWORD else None
    sent = ""
    try:
        previous = saved_session()
        # The login page has already given the new browser a cookie of its
        # own; the kept one replaces it.
        if previous and previous != tab.session_cookie():
            log.info("Restoring the session kept from before the restart.")
            tab.set_session_cookie(previous)
        tab.open(CONSUMPTION_URL)
        while browser.poll() is None:
            if not tab.logged_in():
                save_session("")
                if not auto:
                    log.info("Not logged in. Waiting for a login in the helper browser.")
                wait_for_login(tab, auto)
                log.info("Login detected.")

            tab.allow_cookies()
            cookie = tab.session_cookie()
            if cookie != saved_session():
                save_session(cookie)

            # Until the next check of the portal, keep offering the session
            # to Home Assistant if it did not take it (it may be restarting).
            next_check = time.monotonic() + CHECK_INTERVAL
            while True:
                if cookie and cookie != sent and send_session(cookie):
                    log.info("Session handed to Home Assistant.")
                    sent = cookie
                    dismiss_notification()
                remaining = next_check - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(remaining if cookie == sent or not cookie else min(RETRY_INTERVAL, remaining))
            tab.open(CONSUMPTION_URL)
    finally:
        tab.close()


def main() -> None:
    global HELPER_URL
    if bool(LOGIN_DOCUMENT) != bool(LOGIN_PASSWORD):
        raise SystemExit("Set both CANAL_DOCUMENT and CANAL_PASSWORD (or CANAL_PASSWORD_FILE), or neither")
    if LOGIN_PROFILE not in PROFILES:
        raise SystemExit(f"CANAL_PROFILE must be one of: {', '.join(PROFILES)}")
    if LOGIN_DOCUMENT:
        log.info("Automatic login is on.")
    else:
        log.info("No credentials given: logins are done by hand in the helper browser.")
    if SUPERVISOR_TOKEN and not HELPER_URL:
        HELPER_URL = addon_ingress_url()
    while True:
        browser = None
        try:
            browser = start_browser()
            run(browser)
        except Exception as err:  # the tab was closed, the browser crashed...
            log.warning("Restarting the browser after an error: %s", err)
        finally:
            if browser is not None:
                browser.kill()
                browser.wait()
        time.sleep(5)


if __name__ == "__main__":
    main()
