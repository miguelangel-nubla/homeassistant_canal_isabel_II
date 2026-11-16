# Canal de Isabel II session helper

*[Leer en español](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/blob/main/canal-session-helper/DOCS.md)*

The [Canal de Isabel II][integration] integration reads your water consumption from the virtual office, and logging in to it takes a real browser. This helper is that browser: it runs on your server and logs in for you when the integration needs it.

1. Every minute it asks Home Assistant whether the integration needs a session. That question does not leave your network.
2. If it does, it opens the virtual office and logs in with the document number and the password you entered when adding the integration.
3. It delivers the session to the integration, which downloads the data straight away.
4. Until the next request, about twice a day, it does nothing at the portal.

The helper does not keep your credentials and has nothing to configure about your account: all of that is in the integration.

**Requirement:** the integration has to be [installed][integration] and added in Home Assistant, with your document number and your password.

[![Add the integration to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=canal_de_isabel_ii)

## When the login does not work

The helper fills in the login form and sends it, as you would. Before that it answers "Permitir todas las cookies" (allow all cookies) to the portal's cookie dialog, which covers the page until it is answered.

The form has an invisible captcha that decides by itself whether to let a login through. The helper does not solve it or get around it. It can start asking for challenges or refusing at any time; how to give it the best chances (above all, not using the Canal's website or app at the same time as the helper) is in [the integration's guide](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/blob/main/README.en.md#the-portals-captcha-what-can-go-wrong). When it cannot get in it tells the integration, and Home Assistant is what tells you:

| What happened | What the helper does | What you see in Home Assistant |
|---------------|----------------------|--------------------------------|
| The portal refuses the login | It retries after 1 hour and after 6 more, and then stops insisting: repeating a wrong password could lock the account. | The integration asks for the credentials again. As soon as you enter them, even the same ones, the helper tries again. |
| The captcha asks a person for a check | It leaves it on screen for you to solve and retries after 1 hour. | A notice under **Repairs** with the link to the helper's browser. |
| The portal does not answer or the page does not load | It retries after 5, 15 and 30 minutes, and then every hour. | A notice under **Repairs**. |

Restarts do not change those waits. The notices go away when there is a session.

At any time you can open the helper's browser and log in by hand: the helper notices and delivers that session as if it had logged in itself.

It works out the type of document from the number: NIE if it starts with X, Y or Z, and NIF otherwise.

## As a Home Assistant app

For Home Assistant OS and Supervised, which have apps (what used to be called add-ons). There is nothing to configure.

1. Add the app's repository:

   [![Add the repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmiguelangel-nubla%2Fhassio-repository)

   By hand: in **Settings > Apps**, open the store, choose **Repositories** in the three-dot menu and add `https://github.com/miguelangel-nubla/hassio-repository`.
2. Install **Ayudante de sesión del Canal de Isabel II** and start it:

   [![Open the app in Home Assistant](https://my.home-assistant.io/badges/supervisor_app.svg)](https://my.home-assistant.io/redirect/supervisor_app/?app=133adb15_canal-session-helper&repository_url=https%3A%2F%2Fgithub.com%2Fmiguelangel-nubla%2Fhassio-repository)

Its **Log** tab should show, within a minute or two, `Logged in.` and `Session handed to Home Assistant.` (see [Checking that it works](#checking-that-it-works)).

Its [web interface](https://my.home-assistant.io/redirect/supervisor_ingress/?addon=133adb15_canal-session-helper) (**Open web UI**, or **Show in sidebar**) shows the browser, in case you ever have to log in by hand.

The app runs with an AppArmor profile of its own, which limits what the browser can do inside its container: it cannot mount anything, touch the kernel's settings or look at other processes, and it keeps only the privileges it needs to start.

Access goes through Home Assistant, which is what identifies the user: no port is published and the helper only accepts connections from Home Assistant. Anyone who can open the app's page can use the browser, which holds your Canal session for as long as it lasts.

## As a Docker container

For any other server. It is the same image: `ghcr.io/miguelangel-nubla/canal-session-helper`.

1. In Home Assistant, with an administrator user, create a **long-lived access token** in [your profile > Security](https://my.home-assistant.io/redirect/profile_security/).
2. Copy [`docker-compose.yml`](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/blob/main/canal-session-helper/docker-compose.yml) and fill in `HA_URL`, `HA_TOKEN` and `VNC_PASSWORD`.
3. Start it with `docker compose up -d` and look at the log with `docker logs canal-session-helper` (see [Checking that it works](#checking-that-it-works)).

The helper only makes calls to Home Assistant; Home Assistant does not need to reach it. At `http://<your-server>:6080/`, with the password of `VNC_PASSWORD`, you see the browser, in case you ever have to log in by hand.

| Variable | What for |
|----------|----------|
| `HA_URL` | Address of Home Assistant as seen from the container. |
| `HA_TOKEN` or `HA_TOKEN_FILE` | The token, or the path of a file that holds it. |
| `VNC_PASSWORD` or `VNC_PASSWORD_FILE` | Password of the remote view. Only the first 8 characters count. |
| `VNC_NO_PASSWORD` | `true` removes the password. Only if port 6080 sits behind a proxy that already identifies the user. |
| `HELPER_URL` | Link to the remote view that will appear in Home Assistant's notices, for example `http://<your-server>:6080/vnc.html?autoconnect=1&resize=scale`. |
| `HA_VERIFY_SSL` | `false` if Home Assistant uses a self-signed certificate. |
| `SCREEN_SIZE` | Size of the browser's screen. `1280x800` by default. |

Only the first three are required. The browser's profile and the count of failed logins are kept in the `/data` volume.

The image starts as root only to take ownership of `/data` and carries on as an unprivileged user. It also works with a fixed user (`user:`), a read-only file system and no capabilities, if `/data` and `/tmp` are writable.

### Updates and state

- **The browser is kept current.** Once a month, if Debian has published a newer Chromium, a maintenance version of the helper is released with it. Update the helper when Home Assistant (or whatever tells you about new images) offers it: an old browser is less secure and the captcha likes it less.
- **State of the container.** The image declares a health check: `docker ps` shows `healthy` while the helper keeps going round its loop. If the loop stops for more than 15 minutes, the helper ends itself so that the container is restarted (`restart: unless-stopped` in Docker; in Home Assistant, with the app's **Watchdog** option on).
- **Where the image comes from.** Each image carries a signed statement that this project's repository built it, and the list of what it contains. Check it with the [GitHub CLI](https://cli.github.com/):

  ```sh
  gh attestation verify oci://ghcr.io/miguelangel-nubla/canal-session-helper:<version> --repo miguelangel-nubla/homeassistant_canal_isabel_II
  ```

### Security

- The remote view shows a browser that holds your Canal session for as long as it lasts. Do not publish port 6080 outside your network and use a password of your own.
- The connection of the remote view is not encrypted. To use it from outside, put it behind a VPN or a proxy with HTTPS.
- The Home Assistant token gives administrator access: treat it as a password. With it the helper receives your Canal credentials from the integration each time it has to log in; it does not keep them.
- Chromium runs without its sandbox, as is usual in containers. Use this browser only for the Canal's portal.

## Checking that it works

The helper's log tells what it does. A login looks like this:

```
Waiting for Home Assistant to want a portal session.
Logging in.
Cookie dialog answered: all cookies allowed.
Logged in.
Session handed to Home Assistant.
```

- After the first line nothing may appear for hours: it means the integration does not need a session.
- `The portal refused the login`, `The captcha of the login form asks for a person` and `The login could not be completed` correspond to the three rows of the table in [When the login does not work](#when-the-login-does-not-work); the next line says when the next try will be.
- `Home Assistant not reachable` means that `HA_URL` is wrong or that Home Assistant is stopped.
- `Home Assistant refused canal_de_isabel_ii/session_request` means that the integration is not installed or is older than 2026.11.6 (HTTP 400), or that the token is not valid or does not belong to an administrator (HTTP 401).

To try a login from scratch in the container, stop it, delete `login_state` and the `profile` folder of the `/data` volume and start it. Then reload the integration in Home Assistant so that it asks for a session, if it has none pending.

[integration]: https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/blob/main/README.en.md
