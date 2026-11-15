# Ayudante de sesión

Contenedor opcional que mantiene una sesión de la oficina virtual en un navegador real y se la entrega a la integración. Sustituye a copiar la cookie `JSESSIONID` a mano con F12.

**No inicia sesión por ti.** El inicio de sesión lo haces tú en el navegador del contenedor, que ves desde cualquier dispositivo de tu red. A partir de ahí todo es automático.

## Qué hace

1. Abre Chromium en la página de la oficina virtual y espera a que inicies sesión.
2. Cuando detecta la sesión, lee la cookie y llama al servicio `canal_de_isabel_ii.set_session` de Home Assistant, que importa los datos al momento.
3. Cada 10 minutos recarga la página de consumo para comprobar que la sesión sigue viva.
4. Cuando el portal cierra la sesión, crea una notificación en Home Assistant con el enlace al navegador para que vuelvas a entrar.

## Puesta en marcha

1. En Home Assistant, crea un **token de acceso de larga duración** (tu perfil > Seguridad) con un usuario administrador.
2. Edita `docker-compose.yml`:

   | Variable | Para qué |
   |----------|----------|
   | `HA_URL` | Dirección de Home Assistant vista desde el contenedor. |
   | `HA_TOKEN` | El token del paso anterior. |
   | `VNC_PASSWORD` | Contraseña de la vista remota. VNC solo usa los 8 primeros caracteres. |
   | `HA_TOKEN_FILE`, `VNC_PASSWORD_FILE` | Opcional. Ruta de un fichero con el secreto, en lugar de la variable. |
   | `HELPER_URL` | Opcional. Enlace a la vista remota que aparecerá en la notificación. |
   | `HA_ENTRY_ID` | Opcional. Solo si tienes varias entradas de la integración. |
   | `CHECK_INTERVAL` | Opcional. Segundos entre comprobaciones (600 por defecto). |
   | `HA_VERIFY_SSL` | Opcional. `false` si Home Assistant usa un certificado autofirmado. |

3. Arranca el contenedor:

   ```sh
   docker compose up -d
   ```

   La imagen se descarga de `ghcr.io/miguelangel-nubla/canal-session-helper`. Para construirla tú mismo, cambia `image:` por `build: .` en `docker-compose.yml`.

4. Abre `http://<tu-servidor>:6080/vnc.html?autoconnect=1&resize=scale`, escribe la contraseña e inicia sesión en la oficina virtual.

La integración tiene que estar ya añadida en Home Assistant. Si todavía no lo está, añádela una vez con la cookie copiada a mano.

## Seguridad

- La vista remota muestra un navegador con tu sesión del Canal iniciada. No publiques el puerto 6080 fuera de tu red y usa una contraseña propia.
- La conexión de la vista remota no va cifrada. Si la necesitas desde fuera, ponla detrás de una VPN o de un proxy con HTTPS.
- Chromium se ejecuta sin su sandbox, como es habitual en contenedores. Usa este navegador solo para el portal del Canal.
- El token de Home Assistant da acceso de administrador: trátalo como una contraseña.
