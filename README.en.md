# Canal de Isabel II for Home Assistant

*[Leer en español](README.md)*

An integration that brings the water consumption of your [Canal de Isabel II](https://oficinavirtual.canaldeisabelsegunda.es/) contract (Madrid) into Home Assistant: the consumption hour by hour, ready for the Energy dashboard, and the meter reading.

The Canal has no public API. The data is read from its virtual office, and logging in to it takes a real browser, because the login form has a captcha. That is why the integration works with a **session helper**: a browser that runs on your server and logs in with your document number and password whenever the integration is about to read data.

The interface of the integration is available in English and Spanish. The names below are the English ones.

## Support the project

Do you find it useful? You can [sponsor it on GitHub](https://github.com/sponsors/miguelangel-nubla). Every contribution helps keep it working when the Canal changes its website.

[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-blue?style=for-the-badge&logo=github-sponsors)](https://github.com/sponsors/miguelangel-nubla)

## What you get

The Canal publishes the data with half a day to a day of delay, so none of this is real time: it describes the last day published.

For each contract of the account, on the device `Canal de Isabel II <contract>`:

| What | What for |
|------|----------|
| Hourly statistic `canal_de_isabel_ii:consumption_<contract>` | History of consumption in liters, hour by hour. It is the one to add to the Energy dashboard. |
| **Meter reading** | Absolute reading in m³, the figure on the bill. |
| **Last day's consumption** | Liters of the last day the Canal has published in full. The date is in the `date` attribute. |
| **Last day's minimum flow** | The liters of the quietest hour of that day. In a house without leaks it is 0. |
| **Possible leak** | Turns on when the meter has not rested for a single hour in the last 48 published hours. Both limits can be adjusted. |
| **Data until** | Up to what time the Canal has published data. Tells you whether it is up to date. |
| **Last hour's consumption** | Liters of the last hour published. Disabled by default: that hour is long past when it is published. |

### Possible leak

In a house there is always some hour of the day, usually in the small hours, in which no water is used. An hour counts as rest when it stays under 1 liter, because meters report a few hundredths of a liter in many hours in which nothing is open. A meter that does not rest for two days in a row is usually a dripping cistern or tap, or a leak after the meter. As the data arrives a day late, this is for leaks that last, not for a burst pipe. Drip irrigation, a water softener or a house where water is used at all hours turn it on too.

Each contract has two settings, in the **Configuration** section of its device, to fit the warning to the house:

| Setting | Default | What for |
|---------|---------|----------|
| **Leak: rest flow** | 1 L/h | Raise it if something in your house uses a little at all hours and you do not want it to count. Lower it to hear about smaller drips. |
| **Leak: hours without rest** | 48 h | Fewer hours warn sooner and are wrong more often; more hours, the other way round. |

The virtual office also has its own consumption alarms (a maximum of liters a day, for example), which notify by SMS. The integration does not read or change them; with **Last day's consumption** you can build your own in Home Assistant.

## Installation

The integration is installed from the Home Assistant **Marketplace** (**Settings > Marketplace**).

[![Open the repository in the Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=miguelangel-nubla&repository=homeassistant_canal_isabel_II&category=integration)

1. Press the button and accept adding the repository. To do it by hand: open the Marketplace, choose **Custom repositories** in the three-dot menu and add `https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II` with the category **Integration**.
2. Download **Canal de Isabel II**.
3. Restart Home Assistant.

Home Assistant 2026.11 or later is required.

Manual installation: copy the folder `custom_components/canal_de_isabel_ii` of this repository into `config/custom_components/` and restart.

## Setup

There are two parts: the integration, which keeps your credentials and downloads the data, and the session helper, which logs in to the virtual office when the integration asks for it.

1. Add the integration and enter your document number (NIF or NIE), your password for the virtual office and the profile you log in with (usually **Particular**):

   [![Add the integration to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=canal_de_isabel_ii)

   By hand: **Settings > Devices & services > Add integration** and search for **Canal de Isabel II**.
2. Install the session helper following [its guide](canal-session-helper/DOCS.en.md). As a Home Assistant app (what used to be called an add-on) there is nothing to configure; as a Docker container it only needs the address of Home Assistant and a token.

Within a minute the helper logs in and the integration downloads the last year of consumption. There is nothing else to do.

### How it works

- The integration reads the data twice a day. The first download brings the last year of hourly consumption; the following ones, the last 30 days, so the hours the Canal publishes late fill in by themselves.
- When it is time to read and it has no valid session, it notes so. The helper asks Home Assistant every minute whether there is work, logs in with your credentials and delivers the session. The integration downloads the data at that moment.
- Between reads nothing is done at the portal: the session is not kept open, it simply expires.

### When you have to step in

Only when the helper cannot get in. Home Assistant tells you in **Settings**, without you having to keep an eye on it:

| What happened | What you see in Home Assistant | What to do |
|---------------|--------------------------------|------------|
| The portal refuses your credentials | The integration asks to re-authenticate | Enter the document number and the password again. |
| The portal asks to solve a captcha | A notice under **Repairs** with a link | Open the helper's browser and log in by hand, once. |
| The portal does not answer or has changed its page | A notice under **Repairs** | Wait: the helper retries. If it keeps happening, open its browser to see what is going on. |
| The helper is not running | A notice under **Repairs** | Start the helper. |

The notices go away by themselves when there is a session again. The details (when it retries, and why it does not insist with a refused password) are in the [helper's guide](canal-session-helper/DOCS.en.md).

Your credentials are kept in Home Assistant, like those of any other integration, and are only typed into the virtual office's login form.

### Changing the account or the settings

- **Document number, password or profile:** on [the integration's page](https://my.home-assistant.io/redirect/integration/?domain=canal_de_isabel_ii), open the three-dot menu of the entry and choose **Reconfigure**. Do it when you change your password at the virtual office, without waiting for the portal to refuse it.
- **Leak warning:** its two limits are in the **Configuration** section of each contract's device (see [Possible leak](#possible-leak)).
- **The helper** has no settings about your account.

### The portal's captcha: what can go wrong

The login form of the virtual office is protected by an invisible captcha (reCAPTCHA). It asks nothing of whoever logs in: it watches each login and decides by itself whether to let it through, show a challenge (picking images, for example) or refuse it. The helper does not solve it or get around it. It logs in with a real browser, from your home and with your account, and so far that is enough to get through.

That has two consequences worth knowing:

- **It can stop working without warning.** The Canal can tighten the captcha, change its form or start asking for challenges, and nobody outside the Canal knows for sure what it takes into account. If that happens the integration stays up but stops receiving new data, and Home Assistant tells you (see [When you have to step in](#when-you-have-to-step-in)).
- **When it asks for a challenge, you have to solve it**, in the helper's browser. Once is usually enough for it to get in by itself again.

To give it the best chances of working without you:

- **Do not use the virtual office or the Canal Clientes app at the same time as the integration.** The integration logs in about twice a day, and each login takes a couple of minutes. Several logins of the same account at once, from different places, are just what these systems find suspicious, and the portal may also close one session when another opens. If you have something to do on the website or in the app, do it and let some time pass; the integration retries by itself.
- **Use a single helper per account.** Two helpers, or two Home Assistant instances with the same account, double the logins.
- **Do not force it.** Restarting the helper or reloading the integration again and again "to try" causes extra logins. The data is a day late anyway: there is nothing to gain.
- **If the password is wrong, correct it as soon as you are asked.** The helper stops insisting after three refusals so that the account is not locked, but refusals count against you too.
- **If it asks for challenges often**, log in by hand in the helper's browser a couple of times: a browser with a history of logins solved by a person tends to get fewer challenges.

None of this is a guarantee. The integration depends on a web page that was not made for this; if you know an official way to get the data, [open an issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).

## Energy dashboard

[![Open the Energy configuration](https://my.home-assistant.io/badges/config_energy.svg)](https://my.home-assistant.io/redirect/config_energy/)

In the configuration of the Energy dashboard (**Settings > Dashboards > Energy**), under **Water consumption**, press **Add water source** and choose the statistic **Canal de Isabel II `<contract>`**.

Each import continues the stored series, so downloading the same hours again does not duplicate or distort anything.

> [!IMPORTANT]
> **If you update from 2026.11.9 or earlier:** the hours were stored one hour late. The Canal labels each hour with the moment it ends (today's "00" row is yesterday's last hour) and the integration took it for the moment it starts. On updating, the stored history moves one hour back by itself, once; the liters and the totals do not change, but the split by days does: the last hour of each day goes back to its day.
>
> **If you update from 2026.11.5 or earlier:** update the integration and the helper together. Home Assistant will ask for the document number and the password of the virtual office, which are now kept in the integration; the history is preserved. The helper no longer has options of its own (`document`, `password`, `CANAL_DOCUMENT`, `CANAL_PASSWORD`...) and pasting the cookie by hand is no longer a way to set the integration up.
>
> **If you update from a version before 2026.11:** the history is no longer kept in the sensor `Canal de Isabel II Total`, which is removed. You have to choose the water source again in the Energy dashboard. The old statistics of that sensor can be deleted from [**Developer tools > Statistics**](https://my.home-assistant.io/redirect/tools_statistics/).

## Known limitations

- If the account has several contracts all of them are read, each with its own device, up to a maximum of 20. This could not be tried with a real account with several contracts: if you have one and something is off, [open an issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).
- On the night of the autumn clock change the portal publishes a single row for the two hours called 02:00. In Home Assistant that row lands on one hour and the next one is empty.

## Reference

### Diagnostics

**Download diagnostics**, on [the integration's page](https://my.home-assistant.io/redirect/integration/?domain=canal_de_isabel_ii), shows whether a session has been asked for and since when, when the helper last asked for work, and the history of sessions (when each was delivered, how many reads it served and when the portal rejected it). It never includes the credentials or the cookie.

### Services for the helper

The integration does not call the helper: it is the helper that calls these services, which only administrators may use. There is no need to call them by hand; they are documented for anyone who wants to replace the helper with another tool.

| Service | What for |
|---------|----------|
| `canal_de_isabel_ii.session_request` | Returns the entries that need a session, with their credentials. It has to be called asking for the response (`return_response`). |
| `canal_de_isabel_ii.set_session` | Delivers the `JSESSIONID` cookie of a logged-in session (`jsessionid`, and `entry_id` if there is more than one entry). The integration checks it and downloads the data. |
| `canal_de_isabel_ii.report_login` | Says that the login did not work: `result` (`refused`, `challenge` or `failed`) and, optionally, `detail`, `retry_at` and `helper_url`. |

## Development

The tests, the local Home Assistant instance and the virtual machine for trying the helper as an app are described in [`dev/README.md`](dev/README.md).

If you know of an official API or a better way to get the data, open an [issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).
