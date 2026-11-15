"""Constants for the Canal de Isabel II integration."""
from datetime import timedelta

DOMAIN = "canal_de_isabel_ii"

CONF_JSESSIONID = "jsessionid"
CONF_SESSION_SET_AT = "session_set_at"

# How often the session is checked. A compromise between staying under the
# portal's idle timeout and not hammering its website.
KEEP_ALIVE_INTERVAL = timedelta(minutes=10)

SERVICE_SET_SESSION = "set_session"

SESSION_OK = "ok"
SESSION_EXPIRED = "expired"
SESSION_ERROR = "error"

DEFAULT_NAME = "Canal de Isabel II"

BASE_URL = "https://oficinavirtual.canaldeisabelsegunda.es"
CONSUMPTION_URL = f"{BASE_URL}/group/ovir/consumo"
