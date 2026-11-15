# Canal de Isabel II session helper

The [Canal de Isabel II integration][integration] reads your water consumption
with the session of a browser that is logged in to the virtual office. This
add-on is that browser: it runs inside Home Assistant, you log in through it,
and it passes the session to the integration and keeps it alive.

The add-on never types or submits your credentials. You log in yourself, as
you would in any browser.

## Requirements

The integration must already be installed and added (**Settings > Devices &
services**). If it is asking for a new session, leave that request open: the
add-on answers it.

## Use

1. Start the add-on and open its web interface (**Open web UI**, or enable
   **Show in sidebar**).
2. A browser window shows the virtual office. Log in.
3. When the consumption page appears, the add-on hands the session to the
   integration. Nothing else is needed.

The add-on then checks the session every few minutes. When the portal ends
it, a notification in Home Assistant asks you to log in again.

## Options

| Option | Meaning |
|---|---|
| `check_interval` | Seconds between session checks. Default 600. |
| `entry_id` | Only when the integration is set up more than once: the entry that receives the session. |

## Notes

- Access goes through Home Assistant, so anyone who can open the add-on's
  page can use the logged-in browser. No port is published.
- The browser profile is kept in the add-on's data, so a restart keeps the
  session while the portal still accepts it.
- How long the portal keeps a session is not documented.

[integration]: https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II
