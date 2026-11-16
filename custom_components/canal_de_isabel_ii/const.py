"""Constants for the Canal de Isabel II integration."""
from datetime import timedelta

DOMAIN = "canal_de_isabel_ii"

# The account of the virtual office. The session helper logs in with it.
CONF_DOCUMENT = "document"
CONF_PASSWORD = "password"
CONF_PROFILE = "profile"
# When the credentials were last entered. Entering them again, even the
# same ones, tells the helper to try a login it had given up on.
CONF_CREDENTIALS_SET_AT = "credentials_set_at"
# The profiles of the portal's login form.
PROFILES = ["particular", "empresa", "administrador", "entidad_publica"]
DEFAULT_PROFILE = "particular"

# The portal session the helper delivered last, and when.
CONF_JSESSIONID = "jsessionid"
CONF_SESSION_SET_AT = "session_set_at"

# Set once the long first download has been imported.
CONF_HISTORY_IMPORTED = "history_imported"

# Days of hourly data requested: the whole year the first time, then a
# window wide enough to cover a long outage and readings published late.
# The portal answers a full year in a single request (checked 2026-11).
HISTORY_DAYS = 365
REFRESH_DAYS = 30

# How often the data is fetched, and how soon again after a fetch that failed
# for a reason other than the session. The portal publishes each day's data
# with half a day to a day of delay, so there is nothing to gain from more.
REFRESH_INTERVAL = timedelta(hours=12)
RETRY_INTERVAL = timedelta(minutes=10)

# A session is wanted and no helper has asked for work in this long: the
# helper is not installed, not running or cannot reach Home Assistant.
HELPER_TIMEOUT = timedelta(minutes=10)
HELPER_WATCH_INTERVAL = timedelta(minutes=5)

# The services the session helper works with.
SERVICE_SESSION_REQUEST = "session_request"
SERVICE_SET_SESSION = "set_session"
SERVICE_REPORT_LOGIN = "report_login"

# How a login the helper could not complete ended.
LOGIN_REFUSED = "refused"      # the portal did not accept the credentials
LOGIN_CHALLENGE = "challenge"  # the captcha wants a person
LOGIN_FAILED = "failed"        # the portal did not answer as expected
LOGIN_RESULTS = [LOGIN_REFUSED, LOGIN_CHALLENGE, LOGIN_FAILED]

ISSUE_HELPER_MISSING = "helper_missing"
ISSUE_LOGIN = "login_needs_a_person"

SESSION_OK = "ok"
SESSION_EXPIRED = "expired"
SESSION_ERROR = "error"

DEFAULT_NAME = "Canal de Isabel II"
HELPER_DOCS_URL = (
    "https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II"
    "/blob/main/canal-session-helper/DOCS.md"
)

BASE_URL = "https://oficinavirtual.canaldeisabelsegunda.es"
CONSUMPTION_URL = f"{BASE_URL}/group/ovir/consumo"
