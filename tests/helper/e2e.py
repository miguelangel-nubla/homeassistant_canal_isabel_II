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
SET_SESSION = "canal_de_isabel_ii/set_session"
NOTIFY = "persistent_notification/create"


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
            "CHECK_INTERVAL": "5",
            "LOGIN_TIMEOUT": "20",
            **env,
        }
        args = ["run", "-d", "--add-host", "host.docker.internal:host-gateway", "-v", f"{volume}:/data"]
        for name, value in settings.items():
            args += ["-e", f"{name}={value}"]
        self.id = docker(*args, image)

    def logs(self) -> str:
        return docker("logs", self.id, check=False)

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


def logs_in_and_again_when_the_session_ends(start, state) -> None:
    helper = start(CANAL_DOCUMENT=fake_portal.DOCUMENT.lower(), CANAL_PASSWORD=fake_portal.PASSWORD)
    first = wait_until("the session to reach Home Assistant", lambda: state.calls(SET_SESSION))[0]
    assert first["jsessionid"] in state.sessions, first

    with state.lock:
        state.sessions.clear()  # the portal ends the session
    wait_until("a second session", lambda: len(state.calls(SET_SESSION)) > 1)
    second = state.calls(SET_SESSION)[-1]
    assert second["jsessionid"] in state.sessions and second != first, second

    assert len(state.login_posts) == 2, state.login_posts
    assert not state.calls(NOTIFY), state.calls(NOTIFY)
    assert fake_portal.PASSWORD not in helper.logs()


def a_refused_login_is_not_repeated(start, state) -> None:
    start(CANAL_DOCUMENT=fake_portal.DOCUMENT, CANAL_PASSWORD="wrong")
    message = wait_until("the notification", lambda: state.calls(NOTIFY))[0]["message"]
    assert "rechazado" in message and "Usuario o contraseña incorrectos" in message, message
    assert "Se volverá a intentar a las" in message, message
    time.sleep(20)
    assert len(state.login_posts) == 1, state.login_posts

    # A restart is not a way to try again...
    with state.lock:
        state.ha_calls.clear()
    start(CANAL_DOCUMENT=fake_portal.DOCUMENT, CANAL_PASSWORD="wrong")
    message = wait_until("the notification after a restart", lambda: state.calls(NOTIFY))[0]["message"]
    assert "en pausa" in message, message
    time.sleep(10)
    assert len(state.login_posts) == 1, state.login_posts

    # ...but new credentials are.
    start(CANAL_DOCUMENT=fake_portal.DOCUMENT, CANAL_PASSWORD=fake_portal.PASSWORD)
    wait_until("the session after the password was corrected", lambda: state.calls(SET_SESSION))
    assert len(state.login_posts) == 2, state.login_posts


def a_document_the_form_does_not_accept(start, state) -> None:
    start(CANAL_DOCUMENT="not-a-document", CANAL_PASSWORD=fake_portal.PASSWORD)
    message = wait_until("the notification", lambda: state.calls(NOTIFY))[0]["message"]
    assert "Introduzca un número de documento correcto" in message, message
    assert not state.login_posts, state.login_posts


def a_captcha_challenge_asks_for_a_person(start, state) -> None:
    with state.lock:
        state.challenge = True
    start(CANAL_DOCUMENT=fake_portal.DOCUMENT, CANAL_PASSWORD=fake_portal.PASSWORD)
    message = wait_until("the notification", lambda: state.calls(NOTIFY))[0]["message"]
    assert "captcha" in message, message
    assert not state.login_posts, state.login_posts


def without_credentials_a_person_is_asked(start, state) -> None:
    start()
    message = wait_until("the notification", lambda: state.calls(NOTIFY))[0]["message"]
    assert message.startswith("No hay ninguna sesión activa"), message
    time.sleep(10)
    assert not state.login_posts, state.login_posts


SCENARIOS = [
    logs_in_and_again_when_the_session_ends,
    a_refused_login_is_not_repeated,
    a_document_the_form_does_not_accept,
    a_captcha_challenge_asks_for_a_person,
    without_credentials_a_person_is_asked,
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
