# Development

User documentation is in the [main README](../README.md) (integration) and in [`canal-session-helper/DOCS.md`](../canal-session-helper/DOCS.md) (session helper). This page is about working on the code.

## Layout

| Path | What |
|---|---|
| `custom_components/canal_de_isabel_ii/` | The integration. `csv_parser.py`, `statistics_helpers.py` and `meter_parser.py` have no Home Assistant imports and are tested on their own. |
| `canal-session-helper/` | The session helper: one image, used as a plain container and as a Home Assistant add-on (`config.yaml`). |
| `tests/` | Unit tests; `tests/ha/` runs the integration inside a real Home Assistant with a fake portal; `tests/helper/` runs the session helper's image against a fake portal and a fake integration. |
| `dev/` | The tools below. |

## How the two halves talk

The helper is a client of Home Assistant and nothing calls it, so it needs no address or port known to Home Assistant, as an app or as a container. The integration keeps, per entry, whether a portal session is wanted (a fetch is due and the stored session is missing or was rejected). The helper calls three admin services:

| Service | When | What the integration does |
|---|---|---|
| `session_request` (returns a response) | every minute | answers with the entries that want a session and their credentials; notes that a helper is alive |
| `set_session` | after a login | checks the cookie against the portal, stores it and fetches |
| `report_login` | when a login did not work | `refused` starts the re-authentication flow and stops offering those credentials; `challenge` and `failed` raise a repair issue |

No session is kept alive: a fetch that finds the session gone asks for a new one and keeps the previous data meanwhile. The helper's retry limits live in the helper (`/data/login_state`), so that neither a restart of it nor of Home Assistant can repeat a refused password.

## Tests

```sh
pip install -r requirements-test.txt
pytest
```

CI runs the same suite, hassfest and the Marketplace validation on every pull request.

The session helper has its own end-to-end test, which needs Docker. It builds the image and lets its browser log in to `tests/helper/fake_portal.py`, a stand-in for the virtual office and for Home Assistant:

```sh
python3 tests/helper/e2e.py                        # every scenario, about three minutes
python3 tests/helper/e2e.py a_refused_login_is_not_repeated
```

CI runs it before publishing the image. The fake login page copies the ids and the behaviour of the real one (checked 2026-11-16), including the cookie dialog that covers the login button: when the portal changes its page, update both `LOGIN_PAGE` there and the selectors at the top of `canal-session-helper/helper.py`.

The fake portal cannot show what the real one does with a new browser. Before releasing a change to the login, also start the image against the real portal with an empty `/data`.

## A local Home Assistant with the integration

A throwaway Home Assistant in Docker with the working copy of the integration mounted, for trying changes against the real portal before releasing them.

```sh
docker compose -f dev/docker-compose.yml up -d     # http://localhost:18123, user dev / dev-dev-dev
printf '%s\n%s\n' "<document>" "<password>" | python3 dev/dev.py setup   # first time: creates the user and adds the integration
python3 dev/dev.py wanted                          # what a session helper would be asked to do
echo "<JSESSIONID>" | python3 dev/dev.py session   # deliver a session by hand, as the helper does
python3 dev/dev.py status                          # entry state, sensors, stored statistics
docker compose -f dev/docker-compose.yml restart   # pick up code changes
docker compose -f dev/docker-compose.yml stop      # when done
```

- Without a session helper pointed at it, the instance only gets data from `dev.py session`. The cookie can be the one another Home Assistant is using: the portal accepts the same session from several clients.
- A helper pointed at it logs in to the real portal with the credentials given to `setup`.
- State lives in `dev/config`, which git ignores. It holds the credentials, the session cookie and your consumption data; delete the folder to start over.

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
3. The release builds the helper image tagged `<version>`. With the `DISPATCH_TOKEN` secret set it also tells [`hassio-repository`](https://github.com/miguelangel-nubla/hassio-repository) to pick up the new add-on version; without it, send that repository an `update` dispatch with `app: canal-session-helper` by hand.

## Marketplace listing

The integration is installable today as a custom repository. Inclusion in the default Marketplace catalog was requested on 2026-11-16 in [hacs/default#14264](https://github.com/hacs/default/pull/14264); reviews there take months.

While that pull request is open, and afterwards to stay listed:

- `Marketplace validation` (`.github/workflows/validate.yaml`) and hassfest must keep passing, without ignored checks.
- `hacs.json` needs at least `name`, and `manifest.json` needs `documentation`, `issue_tracker`, `codeowners` and a `version` that matches the release.
- The brand images live in `custom_components/canal_de_isabel_ii/brand/`.
- The repository keeps its description, topics and issues enabled, and publishes full releases, not just tags.
- Do not request reviews on the catalog pull request. Changes to it are pushed to the branch `add-canal-de-isabel-ii` of the fork `miguelangel-nubla/default`.
