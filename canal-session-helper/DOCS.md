# Ayudante de sesión del Canal de Isabel II

La integración [Canal de Isabel II][integration] lee tu consumo de agua con la sesión de un navegador que ha iniciado sesión en la oficina virtual. Este ayudante es ese navegador: se ejecuta en tu servidor e inicia sesión por ti.

1. Abre la oficina virtual e inicia sesión con tu documento y tu contraseña.
2. Entrega la sesión a la integración, que importa los datos al momento.
3. Cada 10 minutos comprueba que la sesión sigue viva.
4. Cuando el portal la cierra, vuelve a iniciar sesión.

La sesión se conserva aunque el ayudante se reinicie, mientras el portal la siga aceptando. El portal no documenta cuánto dura una sesión.

**Requisito:** la integración tiene que estar [instalada][integration] y añadida en Home Assistant. Al añadirla, deja el campo de la cookie vacío: la sesión la entrega el ayudante. Si ya la tenías y está pidiendo una sesión nueva, deja ese aviso como está: desaparece cuando el ayudante entrega la sesión.

[![Añadir la integración a Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=canal_de_isabel_ii)

## Inicio de sesión automático

Con tu documento (NIF o NIE) y tu contraseña de la oficina virtual, el ayudante rellena el formulario de acceso y lo envía, igual que lo harías tú. Las credenciales solo se escriben en ese formulario; no se envían a Home Assistant ni aparecen en el registro.

El portal pregunta por las cookies con un diálogo que tapa la página hasta que se responde. El ayudante responde «Permitir todas las cookies», porque con menos cookies partes del portal pueden no funcionar.

El formulario lleva un captcha invisible que decide por su cuenta si deja pasar. El ayudante no lo resuelve ni lo esquiva. Cuando el inicio de sesión no sale, crea una notificación en Home Assistant con el motivo y un enlace a su navegador, donde puedes entrar tú:

| Qué ha pasado | Qué hace el ayudante |
|---------------|----------------------|
| El portal rechaza el inicio de sesión | Lo reintenta al cabo de 1 hora y de 6 horas más. Si sigue rechazado, no lo intenta más hasta que cambies las credenciales o inicies sesión a mano: repetir una contraseña incorrecta podría bloquear la cuenta. |
| El captcha pide una comprobación a una persona | La deja en pantalla para que la resuelvas y lo reintenta al cabo de 1 hora. |
| El portal no responde o la página no carga | Lo reintenta a los 5, 15 y 30 minutos, y después cada hora. |

Los reinicios no cambian esas esperas. Si entras tú a mano, el ayudante sigue como si hubiera entrado él.

El perfil con el que entra es **Particular**, salvo que le indiques otro. El tipo de documento lo deduce del número: NIE si empieza por X, Y o Z, y NIF en los demás casos.

Sin credenciales el ayudante no inicia sesión: espera a que lo hagas tú en su navegador y te avisa cada vez que el portal cierra la sesión.

## Como aplicación de Home Assistant

Para Home Assistant OS y Supervised, donde hay aplicaciones (lo que antes se llamaba complementos). No hay token de Home Assistant que configurar.

1. Añade el repositorio de la aplicación:

   [![Añadir el repositorio a Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmiguelangel-nubla%2Fhassio-repository)

   A mano: en **Ajustes > Aplicaciones**, abre la tienda, elige **Repositorios** en el menú de los tres puntos y añade `https://github.com/miguelangel-nubla/hassio-repository`.
2. Instala **Ayudante de sesión del Canal de Isabel II**:

   [![Abrir la aplicación en Home Assistant](https://my.home-assistant.io/badges/supervisor_app.svg)](https://my.home-assistant.io/redirect/supervisor_app/?app=133adb15_canal-session-helper&repository_url=https%3A%2F%2Fgithub.com%2Fmiguelangel-nubla%2Fhassio-repository)
3. En su pestaña **Configuración**, escribe tu documento y tu contraseña de la oficina virtual, y guarda.
4. Iníciala.

En su pestaña **Registro** debe aparecer, al cabo de unos segundos, `Logged in.` y `Session handed to Home Assistant.` (ver [Comprobar que funciona](#comprobar-que-funciona)).

Su [interfaz web](https://my.home-assistant.io/redirect/supervisor_ingress/?addon=133adb15_canal-session-helper) (**Abrir interfaz web**, o **Mostrar en la barra lateral**) muestra el navegador, por si alguna vez tienes que iniciar sesión a mano.

| Opción | Para qué |
|--------|----------|
| `document` | Tu NIF o NIE de la oficina virtual. |
| `password` | Tu contraseña de la oficina virtual. |
| `profile` | El perfil que eliges al entrar: `particular` (por defecto), `empresa`, `administrador` o `entidad_publica`. |
| `check_interval` | Segundos entre comprobaciones de la sesión. 600 por defecto. |
| `entry_id` | Solo si la integración está añadida más de una vez: la entrada que recibe la sesión. |

El acceso pasa por Home Assistant, que es quien identifica al usuario: no se publica ningún puerto y el ayudante solo acepta conexiones de Home Assistant. Cualquiera que pueda abrir la página de la aplicación puede usar el navegador con tu sesión iniciada, y cualquier administrador puede ver su configuración.

## Como contenedor Docker

Para cualquier otro servidor. Es la misma imagen: `ghcr.io/miguelangel-nubla/canal-session-helper`.

1. En Home Assistant, con un usuario administrador, crea un **token de acceso de larga duración** en [tu perfil > Seguridad](https://my.home-assistant.io/redirect/profile_security/).
2. Copia [`docker-compose.yml`](docker-compose.yml) y rellena `HA_URL`, `HA_TOKEN`, `VNC_PASSWORD`, `CANAL_DOCUMENT` y `CANAL_PASSWORD`.
3. Arranca con `docker compose up -d` y mira el registro con `docker logs canal-session-helper` (ver [Comprobar que funciona](#comprobar-que-funciona)).

En `http://<tu-servidor>:6080/`, con la contraseña de `VNC_PASSWORD`, se ve el navegador, por si alguna vez tienes que iniciar sesión a mano.

| Variable | Para qué |
|----------|----------|
| `HA_URL` | Dirección de Home Assistant vista desde el contenedor. |
| `HA_TOKEN` o `HA_TOKEN_FILE` | El token, o la ruta de un fichero que lo contiene. |
| `VNC_PASSWORD` o `VNC_PASSWORD_FILE` | Contraseña de la vista remota. Solo cuentan los 8 primeros caracteres. |
| `CANAL_DOCUMENT` | Tu NIF o NIE de la oficina virtual. |
| `CANAL_PASSWORD` o `CANAL_PASSWORD_FILE` | Tu contraseña de la oficina virtual, o la ruta de un fichero que la contiene. |
| `CANAL_PROFILE` | El perfil que eliges al entrar: `particular` (por defecto), `empresa`, `administrador` o `entidad_publica`. |
| `VNC_NO_PASSWORD` | `true` quita la contraseña. Solo si el puerto 6080 queda detrás de un proxy que ya identifica al usuario. |
| `HELPER_URL` | Enlace a la vista remota que aparecerá en la notificación, por ejemplo `http://<tu-servidor>:6080/vnc.html?autoconnect=1&resize=scale`. |
| `HA_ENTRY_ID` | Solo si la integración está añadida más de una vez. |
| `CHECK_INTERVAL` | Segundos entre comprobaciones. 600 por defecto. |
| `HA_VERIFY_SSL` | `false` si Home Assistant usa un certificado autofirmado. |
| `SCREEN_SIZE` | Tamaño de la pantalla del navegador. `1280x800` por defecto. |

Solo las tres primeras son obligatorias; sin `CANAL_DOCUMENT` y `CANAL_PASSWORD` el inicio de sesión lo haces tú. El perfil del navegador, la copia de la sesión y la cuenta de inicios de sesión rechazados se guardan en el volumen `/data`.

La imagen arranca como root únicamente para hacerse con `/data` y continúa como un usuario sin privilegios. También funciona con un usuario fijado (`user:`), con el sistema de ficheros en solo lectura y sin capacidades, si `/data` y `/tmp` son escribibles.

### Seguridad

- La vista remota muestra un navegador con tu sesión del Canal iniciada. No publiques el puerto 6080 fuera de tu red y usa una contraseña propia.
- La conexión de la vista remota no va cifrada. Para usarla desde fuera, ponla detrás de una VPN o de un proxy con HTTPS.
- El token de Home Assistant da acceso de administrador: trátalo como una contraseña.
- La contraseña de la oficina virtual queda en la configuración del contenedor. Con `CANAL_PASSWORD_FILE` puedes darla como un secreto de Docker en lugar de una variable de entorno.
- Chromium se ejecuta sin su sandbox, como es habitual en contenedores. Usa este navegador solo para el portal del Canal.

## Comprobar que funciona

El registro del ayudante cuenta lo que hace. Un arranque con inicio de sesión automático se ve así:

```
Automatic login is on.
Logging in with the configured credentials.
Cookie dialog answered: all cookies allowed.
Logged in.
Session handed to Home Assistant.
```

- Si conserva una sesión de antes que el portal todavía acepta, no inicia sesión: solo aparece `Session handed to Home Assistant.`
- `The portal refused the login`, `The captcha of the login form asks for a person` y `The login could not be completed` corresponden a las tres filas de la tabla de [Inicio de sesión automático](#inicio-de-sesión-automático); la línea siguiente dice cuándo será el próximo intento.
- `Home Assistant refused canal_de_isabel_ii/set_session` indica que la integración no está añadida, que está añadida más de una vez y falta `entry_id`, o que el token no es de un administrador.

Para probar un inicio de sesión desde cero en el contenedor, páralo, borra `session`, `login_state` y la carpeta `profile` del volumen `/data` (el perfil del navegador también guarda la sesión) y arráncalo.

[integration]: https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II
