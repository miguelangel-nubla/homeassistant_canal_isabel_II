# Ayudante de sesión del Canal de Isabel II

La integración [Canal de Isabel II][integration] lee tu consumo de agua de la oficina virtual, y para entrar en ella hace falta un navegador de verdad. Este ayudante es ese navegador: se ejecuta en tu servidor e inicia sesión por ti cuando la integración lo necesita.

1. Cada minuto pregunta a Home Assistant si la integración necesita una sesión. Esa pregunta no sale de tu red.
2. Si la necesita, abre la oficina virtual e inicia sesión con el documento y la contraseña que escribiste al añadir la integración.
3. Entrega la sesión a la integración, que descarga los datos al momento.
4. Hasta la siguiente petición, unas dos veces al día, no hace nada en el portal.

El ayudante no guarda tus credenciales ni tiene nada que configurar sobre tu cuenta: todo eso está en la integración.

**Requisito:** la integración tiene que estar [instalada][integration] y añadida en Home Assistant, con tu documento y tu contraseña.

[![Añadir la integración a Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=canal_de_isabel_ii)

## Cuando el inicio de sesión no sale

El ayudante rellena el formulario de acceso y lo envía, igual que lo harías tú. Antes responde «Permitir todas las cookies» al diálogo de cookies del portal, que tapa la página hasta que se responde.

El formulario lleva un captcha invisible que decide por su cuenta si deja pasar. El ayudante no lo resuelve ni lo esquiva. Puede empezar a pedir pruebas o a rechazar en cualquier momento; cómo darle las mejores opciones (sobre todo, no usar la web ni la app del Canal a la vez que el ayudante) está en [la guía de la integración](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II#el-captcha-del-portal-qué-puede-fallar). Cuando no consigue entrar se lo cuenta a la integración, y es Home Assistant quien te avisa:

| Qué ha pasado | Qué hace el ayudante | Qué ves en Home Assistant |
|---------------|----------------------|---------------------------|
| El portal rechaza el inicio de sesión | Lo reintenta al cabo de 1 hora y de 6 horas más, y después no insiste: repetir una contraseña incorrecta podría bloquear la cuenta. | La integración pide las credenciales de nuevo. En cuanto las escribes, aunque sean las mismas, el ayudante vuelve a intentarlo. |
| El captcha pide una comprobación a una persona | La deja en pantalla para que la resuelvas y lo reintenta al cabo de 1 hora. | Un aviso en **Reparaciones** con el enlace al navegador del ayudante. |
| El portal no responde o la página no carga | Lo reintenta a los 5, 15 y 30 minutos, y después cada hora. | Un aviso en **Reparaciones**. |

Los reinicios no cambian esas esperas. Los avisos desaparecen cuando hay sesión.

En cualquier momento puedes abrir el navegador del ayudante e iniciar sesión a mano: el ayudante lo detecta y entrega esa sesión como si hubiera entrado él.

El tipo de documento lo deduce del número: NIE si empieza por X, Y o Z, y NIF en los demás casos.

## Como aplicación de Home Assistant

Para Home Assistant OS y Supervised, donde hay aplicaciones (lo que antes se llamaba complementos). No hay nada que configurar.

1. Añade el repositorio de la aplicación:

   [![Añadir el repositorio a Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmiguelangel-nubla%2Fhassio-repository)

   A mano: en **Ajustes > Aplicaciones**, abre la tienda, elige **Repositorios** en el menú de los tres puntos y añade `https://github.com/miguelangel-nubla/hassio-repository`.
2. Instala **Ayudante de sesión del Canal de Isabel II** e iníciala:

   [![Abrir la aplicación en Home Assistant](https://my.home-assistant.io/badges/supervisor_app.svg)](https://my.home-assistant.io/redirect/supervisor_app/?app=133adb15_canal-session-helper&repository_url=https%3A%2F%2Fgithub.com%2Fmiguelangel-nubla%2Fhassio-repository)

En su pestaña **Registro** debe aparecer, en un minuto o dos, `Logged in.` y `Session handed to Home Assistant.` (ver [Comprobar que funciona](#comprobar-que-funciona)).

Su [interfaz web](https://my.home-assistant.io/redirect/supervisor_ingress/?addon=133adb15_canal-session-helper) (**Abrir interfaz web**, o **Mostrar en la barra lateral**) muestra el navegador, por si alguna vez tienes que iniciar sesión a mano.

La aplicación se ejecuta con un perfil de AppArmor propio, que limita lo que el navegador puede hacer dentro de su contenedor: no puede montar nada, ni tocar los ajustes del núcleo, ni mirar otros procesos, y solo conserva los privilegios que necesita para arrancar.

El acceso pasa por Home Assistant, que es quien identifica al usuario: no se publica ningún puerto y el ayudante solo acepta conexiones de Home Assistant. Cualquiera que pueda abrir la página de la aplicación puede usar el navegador, que tendrá tu sesión del Canal iniciada mientras dure.

## Como contenedor Docker

Para cualquier otro servidor. Es la misma imagen: `ghcr.io/miguelangel-nubla/canal-session-helper`.

1. En Home Assistant, con un usuario administrador, crea un **token de acceso de larga duración** en [tu perfil > Seguridad](https://my.home-assistant.io/redirect/profile_security/).
2. Copia [`docker-compose.yml`](docker-compose.yml) y rellena `HA_URL`, `HA_TOKEN` y `VNC_PASSWORD`.
3. Arranca con `docker compose up -d` y mira el registro con `docker logs canal-session-helper` (ver [Comprobar que funciona](#comprobar-que-funciona)).

El ayudante solo hace llamadas hacia Home Assistant; Home Assistant no necesita llegar a él. En `http://<tu-servidor>:6080/`, con la contraseña de `VNC_PASSWORD`, se ve el navegador, por si alguna vez tienes que iniciar sesión a mano.

| Variable | Para qué |
|----------|----------|
| `HA_URL` | Dirección de Home Assistant vista desde el contenedor. |
| `HA_TOKEN` o `HA_TOKEN_FILE` | El token, o la ruta de un fichero que lo contiene. |
| `VNC_PASSWORD` o `VNC_PASSWORD_FILE` | Contraseña de la vista remota. Solo cuentan los 8 primeros caracteres. |
| `VNC_NO_PASSWORD` | `true` quita la contraseña. Solo si el puerto 6080 queda detrás de un proxy que ya identifica al usuario. |
| `HELPER_URL` | Enlace a la vista remota que aparecerá en los avisos de Home Assistant, por ejemplo `http://<tu-servidor>:6080/vnc.html?autoconnect=1&resize=scale`. |
| `HA_VERIFY_SSL` | `false` si Home Assistant usa un certificado autofirmado. |
| `SCREEN_SIZE` | Tamaño de la pantalla del navegador. `1280x800` por defecto. |

Solo las tres primeras son obligatorias. El perfil del navegador y la cuenta de inicios de sesión fallidos se guardan en el volumen `/data`.

La imagen arranca como root únicamente para hacerse con `/data` y continúa como un usuario sin privilegios. También funciona con un usuario fijado (`user:`), con el sistema de ficheros en solo lectura y sin capacidades, si `/data` y `/tmp` son escribibles.

### Seguridad

- La vista remota muestra un navegador que tiene tu sesión del Canal iniciada mientras dura. No publiques el puerto 6080 fuera de tu red y usa una contraseña propia.
- La conexión de la vista remota no va cifrada. Para usarla desde fuera, ponla detrás de una VPN o de un proxy con HTTPS.
- El token de Home Assistant da acceso de administrador: trátalo como una contraseña. Con él el ayudante recibe de la integración tus credenciales del Canal cada vez que tiene que iniciar sesión; no las guarda.
- Chromium se ejecuta sin su sandbox, como es habitual en contenedores. Usa este navegador solo para el portal del Canal.

## Comprobar que funciona

El registro del ayudante cuenta lo que hace. Un inicio de sesión se ve así:

```
Waiting for Home Assistant to want a portal session.
Logging in.
Cookie dialog answered: all cookies allowed.
Logged in.
Session handed to Home Assistant.
```

- Después de la primera línea puede no aparecer nada durante horas: significa que la integración no necesita una sesión.
- `The portal refused the login`, `The captcha of the login form asks for a person` y `The login could not be completed` corresponden a las tres filas de la tabla de [Cuando el inicio de sesión no sale](#cuando-el-inicio-de-sesión-no-sale); la línea siguiente dice cuándo será el próximo intento.
- `Home Assistant not reachable` indica que `HA_URL` no es correcta o que Home Assistant está parado.
- `Home Assistant refused canal_de_isabel_ii/session_request` indica que la integración no está instalada o es anterior a 2026.11.6 (HTTP 400), o que el token no vale o no es de un administrador (HTTP 401).

Para probar un inicio de sesión desde cero en el contenedor, páralo, borra `login_state` y la carpeta `profile` del volumen `/data` y arráncalo. Después recarga la integración en Home Assistant para que pida una sesión, si no tiene una pendiente.

[integration]: https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II
