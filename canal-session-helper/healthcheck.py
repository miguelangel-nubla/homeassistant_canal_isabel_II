"""Container health check: is the helper's main loop going round?

The helper writes the time to a file on every pass (heartbeat in helper.py).
Healthy means that the file is recent. The helper also ends itself when its
loop stalls, so that the container is restarted; this check is what shows
the state from outside (docker ps, the Supervisor's watchdog).
"""
import sys
import time

HEARTBEAT_FILE = "/tmp/helper.alive"
# A pass of the loop may take a few minutes while a login is under way.
MAX_AGE = 600

try:
    with open(HEARTBEAT_FILE, encoding="utf-8") as file:
        age = time.time() - int(file.read().strip())
except (OSError, ValueError):
    sys.exit("no sign of life from the helper yet")
if age > MAX_AGE:
    sys.exit(f"the helper has not gone round for {int(age)} seconds")
