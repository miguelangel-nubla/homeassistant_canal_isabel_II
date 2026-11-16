#!/usr/bin/env python3
"""End-to-end test of the session helper: the real image against a fake portal.

    python3 tests/helper/e2e.py            # builds the image first
    python3 tests/helper/e2e.py --image ghcr.io/miguelangel-nubla/canal-session-helper:dev

Needs Docker. The container's browser talks to fake_portal.py on this
machine, which plays the virtual office and Home Assistant.
"""
import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fake_portal  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SET_SESSION = "set_session"
REPORT = "report_login"


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f"docker {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip() + result.stderr.strip()


class Helper:
    """A helper container pointed at the fake portal."""

    def __init__(self, image: str, port: int, volume: str, **env: str) -> None:
        url = f"http://host.docker.internal:{port}"
        settings = {
            "PORTAL_URL": url,
            "HA_URL": url,
            "HA_TOKEN": fake_portal.HA_TOKEN,
            "VNC_NO_PASSWORD": "true",
            "POLL_INTERVAL": "2",
            "REPORT_INTERVAL": "6",
            "LOGIN_TIMEOUT": "20",
            **env,
        }
        args = ["run", "-d", "--add-host", "host.docker.internal:host-gateway", "-v", f"{volume}:/data"]
        for name, value in settings.items():
            args += ["-e", f"{name}={value}"]
        self.id = docker(*args, image)

    def logs(self) -> str:
        return docker("logs", self.id, check=False)

    def healthy(self) -> bool:
        """What the container's own health check says."""
        result = subprocess.run(["docker", "exec", self.id, "python3", "/app/healthcheck.py"], capture_output=True)
        return result.returncode == 0

    def stop(self) -> None:
        docker("rm", "-f", self.id, check=False)


def wait_until(what: str, condition, seconds: int = 120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(1)
    raise AssertionError(f"timed out waiting for {what}")


def sessions(state) -> list:
    return [call["jsessionid"] for call in state.calls(SET_SESSION)]


def reports(state) -> list:
    return state.calls(REPORT)


def logs_in_only_when_a_session_is_wanted(start, state) -> None:
    helper = start()
    time.sleep(10)
    assert state.portal_hits == 0, "the portal was visited with nothing to do there"
    assert helper.healthy(), "idle, the helper should report itself healthy"

    state.want("one", fake_portal.DOCUMENT.lower(), fake_portal.PASSWORD)
    first = wait_until("the session to reach Home Assistant", lambda: sessions(state))[0]
    assert state.sessions[first] == fake_portal.DOCUMENT

    # With the session delivered there is nothing to do at the portal.
    hits = state.portal_hits
    time.sleep(10)
    assert state.portal_hits == hits, "the session is being kept alive"

    with state.lock:
        state.sessions.clear()  # the portal ends the session
    state.want("one", fake_portal.DOCUMENT, fake_portal.PASSWORD)
    wait_until("a second session", lambda: len(sessions(state)) > 1)
    assert sessions(state)[1] in state.sessions and sessions(state)[1] != first

    assert len(state.login_posts) == 2, state.login_posts
    # The cookie dialog was answered with "allow all", once.
    assert [post["cookie_consent"] for post in state.login_posts] == ["all", "all"], state.login_posts
    assert helper.logs().count("Cookie dialog answered") == 1, helper.logs()
    assert not reports(state), reports(state)
    assert fake_portal.PASSWORD not in helper.logs()
    assert helper.healthy()


def each_account_gets_its_own_session(start, state) -> None:
    start()
    state.want("one", fake_portal.DOCUMENT, fake_portal.PASSWORD)
    state.want("two", fake_portal.OTHER_DOCUMENT, fake_portal.OTHER_PASSWORD)
    wait_until("both sessions", lambda: len(sessions(state)) == 2)
    # The fake Home Assistant only takes the session of the entry's account.
    assert not state.wants, state.wants
    assert [post["tipoDocumento"] for post in state.login_posts] == ["NIE", "NIF"], state.login_posts
    assert not reports(state), reports(state)


def a_refused_login_is_reported_and_not_repeated(start, state) -> None:
    start()
    state.want("one", fake_portal.DOCUMENT, "wrong")
    report = wait_until("the report", lambda: reports(state))[0]
    assert report["result"] == "refused" and report["entry_id"] == "one", report
    assert report["detail"] == "Usuario o contraseña incorrectos", report
    assert report["retry_at"].endswith("+00:00"), report

    # Home Assistant forgot (it restarted) and asks again: it is told again,
    # and the portal is not.
    with state.lock:
        state.refused.clear()
    wait_until("the reminder", lambda: len(reports(state)) > 1)
    assert reports(state)[1] == report, reports(state)

    # A restart of the helper is not a way to try again either.
    with state.lock:
        state.refused.clear()
    start()
    wait_until("the reminder after a restart", lambda: len(reports(state)) > 2)
    assert len(state.login_posts) == 1, state.login_posts

    # Entering the credentials again in Home Assistant is, even the same ones.
    state.want("one", fake_portal.DOCUMENT, "wrong", set_at="2")
    wait_until("the report of a second try", lambda: len(reports(state)) > 3)
    assert len(state.login_posts) == 2, state.login_posts
    state.want("one", fake_portal.DOCUMENT, fake_portal.PASSWORD, set_at="3")
    wait_until("the session once the password is right", lambda: sessions(state))
    assert len(state.login_posts) == 3, state.login_posts


def a_document_the_form_does_not_accept(start, state) -> None:
    start()
    state.want("one", "not-a-document", fake_portal.PASSWORD)
    report = wait_until("the report", lambda: reports(state))[0]
    assert report["result"] == "refused", report
    assert "Introduzca un número de documento correcto" in report["detail"], report
    assert not state.login_posts, state.login_posts


def a_captcha_challenge_asks_for_a_person(start, state) -> None:
    with state.lock:
        state.challenge = True
    start(HELPER_URL="http://helper.example/")
    state.want("one", fake_portal.DOCUMENT, fake_portal.PASSWORD)
    report = wait_until("the report", lambda: reports(state))[0]
    assert report["result"] == "challenge" and report["retry_at"], report
    assert report["helper_url"] == "http://helper.example/", report
    assert not state.login_posts, state.login_posts

    # The challenge stays on screen: the portal is left alone meanwhile.
    hits = state.portal_hits
    time.sleep(10)
    assert state.portal_hits == hits, "the login page was reloaded under the challenge"


SCENARIOS = [
    logs_in_only_when_a_session_is_wanted,
    each_account_gets_its_own_session,
    a_refused_login_is_reported_and_not_repeated,
    a_document_the_form_does_not_accept,
    a_captcha_challenge_asks_for_a_person,
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", help="test this image instead of building one")
    parser.add_argument("only", nargs="*", help="names of the scenarios to run (default: all)")
    options = parser.parse_args()

    image = options.image
    if not image:
        image = "canal-session-helper:e2e"
        print("Building the image...", flush=True)
        docker("build", "-q", "-t", image, str(REPO / "canal-session-helper"))

    state = fake_portal.State()
    server = fake_portal.serve(state)
    failed = 0
    for scenario in SCENARIOS:
        if options.only and scenario.__name__ not in options.only:
            continue
        state.reset()
        volume = f"canal-helper-e2e-{uuid.uuid4().hex[:8]}"
        helpers = []

        def start(**env: str) -> Helper:
            # One helper at a time, all of a scenario on the same /data.
            for running in helpers:
                running.stop()
            helpers.append(Helper(image, server.server_port, volume, **env))
            return helpers[-1]

        try:
            scenario(start, state)
            print(f"ok    {scenario.__name__}", flush=True)
        except Exception as err:  # pylint: disable=broad-except
            failed += 1
            print(f"FAIL  {scenario.__name__}: {type(err).__name__}: {err}", flush=True)
            if helpers:
                print(helpers[-1].logs())
        finally:
            for running in helpers:
                running.stop()
            docker("volume", "rm", "-f", volume, check=False)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
