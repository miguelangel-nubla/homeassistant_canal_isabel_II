"""Constants for the Canal de Isabel II integration."""
from datetime import timedelta

DOMAIN = "canal_de_isabel_ii"

CONF_JSESSIONID = "jsessionid"
CONF_SESSION_SET_AT = "session_set_at"

# How often the session is checked. A compromise between staying under the
# portal's idle timeout and not hammering its website.
KEEP_ALIVE_INTERVAL = timedelta(minutes=10)

# Set once the long first download has been imported.
CONF_HISTORY_IMPORTED = "history_imported"

# Days of hourly data requested: the whole year the first time, then a
# window wide enough to cover a long outage and readings published late.
# The portal answers a full year in a single request (checked 2026-11).
HISTORY_DAYS = 365
REFRESH_DAYS = 30

SERVICE_SET_SESSION = "set_session"

SESSION_OK = "ok"
SESSION_EXPIRED = "expired"
SESSION_ERROR = "error"

DEFAULT_NAME = "Canal de Isabel II"

BASE_URL = "https://oficinavirtual.canaldeisabelsegunda.es"
CONSUMPTION_URL = f"{BASE_URL}/group/ovir/consumo"
