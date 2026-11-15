# Local test instance

A throwaway Home Assistant in Docker with the working copy of the integration mounted, for trying changes against the real portal before releasing them.

```sh
docker compose -f dev/docker-compose.yml up -d     # http://localhost:18123, user dev / dev-dev-dev
echo "<JSESSIONID>" | python3 dev/dev.py setup     # first time: creates the user and adds the integration
echo "<JSESSIONID>" | python3 dev/dev.py session   # later: hand it a fresh session
python3 dev/dev.py status                          # entry state, sensors, stored statistics
docker compose -f dev/docker-compose.yml restart   # pick up code changes
docker compose -f dev/docker-compose.yml stop      # when done
```

- The cookie can be the one another Home Assistant is using: the portal accepts the same session from several clients.
- Stop the container when you are not testing. While it runs it checks the session every 10 minutes like any other install, which adds activity to a session whose lifetime is being measured elsewhere.
- State lives in `dev/config`, which git ignores. It holds the session cookie and your consumption data; delete the folder to start over.
