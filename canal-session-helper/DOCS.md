# Ayudante de sesión del Canal de Isabel II

La integración [Canal de Isabel II][integration] lee tu consumo de agua con la sesión de un navegador que ha iniciado sesión en la oficina virtual. Este ayudante es ese navegador: se ejecuta en tu servidor e inicia sesión por ti.

1. Abre la oficina virtual e inicia sesión con tu documento y tu contraseña.
2. Entrega la sesión a la integración, que importa los datos al momento.
3. Cada 10 minutos comprueba que la sesión sigue viva.
4. Cuando el portal la cierra, vuelve a iniciar sesión.

La sesión se conserva aunque el ayudante se reinicie, mientras el portal la siga aceptando. El portal no documenta cuánto dura una sesión.

**Requisito:** la integración tiene que estar instalada y añadida en Home Assistant. Al añadirla, deja el campo de la cookie vacío: la sesión la entrega el ayudante. Si ya la tenías y está pidiendo una sesión nueva, deja ese aviso abierto: el ayudante lo resuelve.

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

Sin credenciales el ayudante no inicia sesión: espera a que lo hagas tú en su navegador y te avisa cada vez que el portal cierra la sesión.

## Como complemento de Home Assistant

Para Home Assistant OS y Supervised. No hay token de Home Assistant que configurar.

1. Añade el repositorio `https://github.com/miguelangel-nubla/hassio-repository` en la tienda de complementos (**Ajustes > Complementos > Tienda > Repositorios**; en versiones recientes, **Ajustes > Aplicaciones**).
2. Instala **Ayudante de sesión del Canal de Isabel II**.
3. En su pestaña **Configuración**, escribe tu documento y tu contraseña de la oficina virtual, y guarda.
4. Inícialo.

Su interfaz web (**Abrir interfaz web**, o **Mostrar en la barra lateral**) muestra el navegador, por si alguna vez tienes que iniciar sesión a mano.

| Opción | Para qué |
|--------|----------|
| `document` | Tu NIF o NIE de la oficina virtual. |
| `password` | Tu contraseña de la oficina virtual. |
| `profile` | El perfil que eliges al entrar: `particular` (por defecto), `empresa`, `administrador` o `entidad_publica`. |
| `check_interval` | Segundos entre comprobaciones de la sesión. 600 por defecto. |
| `entry_id` | Solo si la integración está añadida más de una vez: la entrada que recibe la sesión. |

El acceso pasa por Home Assistant, que es quien identifica al usuario: no se publica ningún puerto y el ayudante solo acepta conexiones de Home Assistant. Cualquiera que pueda abrir la página del complemento puede usar el navegador con tu sesión iniciada.

## Como contenedor Docker

Para cualquier otro servidor. Es la misma imagen: `ghcr.io/miguelangel-nubla/canal-session-helper`.

1. En Home Assistant, crea un **token de acceso de larga duración** (tu perfil > Seguridad) con un usuario administrador.
2. Copia [`docker-compose.yml`](docker-compose.yml) y rellena `HA_URL`, `HA_TOKEN`, `VNC_PASSWORD`, `CANAL_DOCUMENT` y `CANAL_PASSWORD`.
3. Arranca con `docker compose up -d`.

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
| `HELPER_URL` | Enlace a la vista remota que aparecerá en la notificación. |
| `HA_ENTRY_ID` | Solo si la integración está añadida más de una vez. |
| `CHECK_INTERVAL` | Segundos entre comprobaciones. 600 por defecto. |
| `HA_VERIFY_SSL` | `false` si Home Assistant usa un certificado autofirmado. |
| `SCREEN_SIZE` | Tamaño de la pantalla del navegador. `1280x800` por defecto. |

Solo las tres primeras son obligatorias; sin `CANAL_DOCUMENT` y `CANAL_PASSWORD` el inicio de sesión lo haces tú. Los datos del navegador y la copia de la sesión se guardan en el volumen `/data`.

La imagen arranca como root únicamente para hacerse con `/data` y continúa como un usuario sin privilegios. También funciona con un usuario fijado (`user:`), con el sistema de ficheros en solo lectura y sin capacidades, si `/data` y `/tmp` son escribibles.

### Seguridad

- La vista remota muestra un navegador con tu sesión del Canal iniciada. No publiques el puerto 6080 fuera de tu red y usa una contraseña propia.
- La conexión de la vista remota no va cifrada. Para usarla desde fuera, ponla detrás de una VPN o de un proxy con HTTPS.
- El token de Home Assistant da acceso de administrador: trátalo como una contraseña.
- La contraseña de la oficina virtual queda en la configuración del contenedor. Con `CANAL_PASSWORD_FILE` puedes darla como un secreto de Docker en lugar de una variable de entorno.
- Chromium se ejecuta sin su sandbox, como es habitual en contenedores. Usa este navegador solo para el portal del Canal.

[integration]: https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II
