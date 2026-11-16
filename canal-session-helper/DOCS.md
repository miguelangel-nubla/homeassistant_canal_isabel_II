# Ayudante de sesión del Canal de Isabel II

La integración [Canal de Isabel II][integration] lee tu consumo de agua con la sesión de un navegador que ha iniciado sesión en la oficina virtual. Este ayudante es ese navegador: se ejecuta en tu servidor, inicias sesión a través de él, y él hace el resto.

1. Abre la oficina virtual y espera a que inicies sesión. Nunca escribe ni envía tus credenciales.
2. Cuando detecta la sesión, se la entrega a la integración, que importa los datos al momento.
3. Cada 10 minutos comprueba que la sesión sigue viva.
4. Cuando el portal la cierra, crea una notificación en Home Assistant para que vuelvas a entrar.

La sesión se conserva aunque el ayudante se reinicie, mientras el portal la siga aceptando. El portal no documenta cuánto dura una sesión.

**Requisito:** la integración tiene que estar instalada y añadida en Home Assistant. Al añadirla, deja el campo de la cookie vacío: la sesión la entrega el ayudante. Si ya la tenías y está pidiendo una sesión nueva, deja ese aviso abierto: el ayudante lo resuelve.

## Como complemento de Home Assistant

Para Home Assistant OS y Supervised. No hay token ni contraseña que configurar.

1. Añade el repositorio `https://github.com/miguelangel-nubla/hassio-repository` en la tienda de complementos (**Ajustes > Complementos > Tienda > Repositorios**; en versiones recientes, **Ajustes > Aplicaciones**).
2. Instala **Ayudante de sesión del Canal de Isabel II** e inícialo.
3. Abre su interfaz web (**Abrir interfaz web**, o activa **Mostrar en la barra lateral**).
4. Inicia sesión en la oficina virtual.

| Opción | Para qué |
|--------|----------|
| `check_interval` | Segundos entre comprobaciones de la sesión. 600 por defecto. |
| `entry_id` | Solo si la integración está añadida más de una vez: la entrada que recibe la sesión. |

El acceso pasa por Home Assistant, que es quien identifica al usuario: no se publica ningún puerto y el ayudante solo acepta conexiones de Home Assistant. Cualquiera que pueda abrir la página del complemento puede usar el navegador con tu sesión iniciada.

## Como contenedor Docker

Para cualquier otro servidor. Es la misma imagen: `ghcr.io/miguelangel-nubla/canal-session-helper`.

1. En Home Assistant, crea un **token de acceso de larga duración** (tu perfil > Seguridad) con un usuario administrador.
2. Copia [`docker-compose.yml`](docker-compose.yml) y rellena `HA_URL`, `HA_TOKEN` y `VNC_PASSWORD`.
3. Arranca con `docker compose up -d`.
4. Abre `http://<tu-servidor>:6080/`, escribe la contraseña e inicia sesión en la oficina virtual.

| Variable | Para qué |
|----------|----------|
| `HA_URL` | Dirección de Home Assistant vista desde el contenedor. |
| `HA_TOKEN` o `HA_TOKEN_FILE` | El token, o la ruta de un fichero que lo contiene. |
| `VNC_PASSWORD` o `VNC_PASSWORD_FILE` | Contraseña de la vista remota. Solo cuentan los 8 primeros caracteres. |
| `VNC_NO_PASSWORD` | `true` quita la contraseña. Solo si el puerto 6080 queda detrás de un proxy que ya identifica al usuario. |
| `HELPER_URL` | Enlace a la vista remota que aparecerá en la notificación. |
| `HA_ENTRY_ID` | Solo si la integración está añadida más de una vez. |
| `CHECK_INTERVAL` | Segundos entre comprobaciones. 600 por defecto. |
| `HA_VERIFY_SSL` | `false` si Home Assistant usa un certificado autofirmado. |
| `SCREEN_SIZE` | Tamaño de la pantalla del navegador. `1280x800` por defecto. |

Solo las tres primeras son obligatorias. Los datos del navegador y la copia de la sesión se guardan en el volumen `/data`.

La imagen arranca como root únicamente para hacerse con `/data` y continúa como un usuario sin privilegios. También funciona con un usuario fijado (`user:`), con el sistema de ficheros en solo lectura y sin capacidades, si `/data` y `/tmp` son escribibles.

### Seguridad

- La vista remota muestra un navegador con tu sesión del Canal iniciada. No publiques el puerto 6080 fuera de tu red y usa una contraseña propia.
- La conexión de la vista remota no va cifrada. Para usarla desde fuera, ponla detrás de una VPN o de un proxy con HTTPS.
- El token de Home Assistant da acceso de administrador: trátalo como una contraseña.
- Chromium se ejecuta sin su sandbox, como es habitual en contenedores. Usa este navegador solo para el portal del Canal.

[integration]: https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II
