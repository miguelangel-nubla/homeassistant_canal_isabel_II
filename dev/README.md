# Development

User documentation is in the [main README](../README.md) (integration) and in [`canal-session-helper/DOCS.md`](../canal-session-helper/DOCS.md) (session helper). This page is about working on the code.

## Layout

| Path | What |
|---|---|
| `custom_components/canal_de_isabel_ii/` | The integration. `csv_parser.py`, `statistics_helpers.py` and `meter_parser.py` have no Home Assistant imports and are tested on their own. |
| `canal-session-helper/` | The session helper: one image, used as a plain container and as a Home Assistant add-on (`config.yaml`). |
| `tests/` | Unit tests; `tests/ha/` runs the integration inside a real Home Assistant with a fake portal. |
| `dev/` | The tools below. |

## Tests

```sh
pip install -r requirements-test.txt
pytest
```

CI runs the same suite, hassfest and the Marketplace validation on every pull request.

## A local Home Assistant with the integration

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
- Stop the container when you are not testing. While it runs it checks the session every 10 minutes like any other install.
- State lives in `dev/config`, which git ignores. It holds the session cookie and your consumption data; delete the folder to start over.

## A local Home Assistant OS, for the add-on

The add-on only fully runs under a Supervisor. `dev/haos.sh` starts Home Assistant OS in QEMU on an Apple silicon Mac.

```sh
brew install qemu
# put the generic-aarch64 .qcow2 image from the Home Assistant OS releases at dev/haos/haos.qcow2
dev/haos.sh start                                  # http://localhost:18124 after a minute or two
dev/haos.sh stop
```

- `dev/console.py '<command>'` runs a command on the VM's console, for example `ha supervisor info`.
- `dev/haos_addon.py <method> <endpoint> [json]` calls the Supervisor API (add a repository, install or start an add-on). It needs `aiohttp` and these variables, which also point `dev/dev.py` at the VM: `DEV_HA_URL=http://127.0.0.1:18124 DEV_HA_STATE=dev/haos`.
- Home Assistant OS 18 serves its web interface on port 80, which is what `haos.sh` forwards.
- The VM's disk is in `dev/haos`, which git ignores.

## Releasing

1. Set `version` in `custom_components/canal_de_isabel_ii/manifest.json` and merge.
2. Publish a GitHub release tagged `v<version>` on `main`.
3. The release builds the helper image tagged `<version>`. With the `DISPATCH_TOKEN` secret set it also tells [`hassio-repository`](https://github.com/miguelangel-nubla/hassio-repository) to pick up the new add-on version; without it, send that repository an `update` dispatch for `canal-session-helper` by hand.
