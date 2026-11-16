# Canal de Isabel II para Home Assistant

*[Read in English](README.en.md)*

Integración que lleva a Home Assistant el consumo de agua de tu contrato del [Canal de Isabel II](https://oficinavirtual.canaldeisabelsegunda.es/) (Madrid): el consumo hora a hora, listo para el panel de Energía, y la lectura del contador.

El Canal no ofrece una API pública. Los datos se leen de la oficina virtual, y para entrar en ella hace falta un navegador de verdad, porque su formulario de acceso lleva un captcha. Por eso la integración trabaja con un **ayudante de sesión**: un navegador que se ejecuta en tu servidor e inicia sesión con tu documento y tu contraseña cada vez que la integración va a leer datos.

## Apoya el proyecto

¿Te resulta útil? Puedes [patrocinarlo en GitHub](https://github.com/sponsors/miguelangel-nubla). Cada aportación ayuda a mantenerlo al día cuando el Canal cambia su web.

[![Patrocinar en GitHub](https://img.shields.io/badge/Patrocinar-GitHub-blue?style=for-the-badge&logo=github-sponsors)](https://github.com/sponsors/miguelangel-nubla)

## Qué obtienes

El Canal publica los datos con medio día o un día de retraso, así que nada de esto es en tiempo real: describe el último día publicado.

Por cada contrato de la cuenta, en el dispositivo `Canal de Isabel II <contrato>`:

| Qué | Para qué |
|-----|----------|
| Estadística horaria `canal_de_isabel_ii:consumption_<contrato>` | Histórico de consumo en litros, hora a hora. Es la que se añade al panel de Energía. |
| **Lectura del contador** | Lectura absoluta en m³, la cifra que aparece en la factura. |
| **Consumo del último día** | Litros del último día que el Canal ha publicado completo. La fecha va en el atributo `date`. |
| **Caudal mínimo del último día** | Los litros de la hora más tranquila de ese día. En una casa sin fugas es 0. |
| **Posible fuga** | Se activa cuando el contador no ha descansado ni una hora en las últimas 48 horas publicadas. Los dos límites se pueden ajustar. |
| **Datos hasta** | Hasta qué hora ha publicado datos el Canal. Sirve para saber si están al día. |
| **Consumo de la última hora** | Litros de la última hora publicada. Desactivado por defecto: esa hora ya pasó hace mucho cuando se publica. |

### Posible fuga

En una casa siempre hay alguna hora del día, normalmente de madrugada, en la que no se gasta nada. Se cuenta como hora de descanso la que no llega a 1 litro, porque los contadores apuntan unas centésimas de litro en muchas horas en las que no hay nada abierto. Un contador que no descansa durante dos días seguidos suele ser una cisterna o un grifo que gotea, o una fuga después del contador. Como los datos llegan con un día de retraso, sirve para las fugas que duran, no para una rotura. Un riego por goteo, un descalcificador o una casa en la que se usa agua a todas horas también lo activan.

Cada contrato tiene dos ajustes, en la sección **Configuración** de su dispositivo, para adaptar el aviso a la casa:

| Ajuste | Por defecto | Para qué |
|--------|-------------|----------|
| **Fuga: caudal de reposo** | 1 L/h | Súbelo si en tu casa hay algo que gasta un poco a todas horas y no quieres que cuente. Bájalo para enterarte de goteos más pequeños. |
| **Fuga: horas sin reposo** | 48 h | Menos horas avisan antes y se equivocan más; más horas, al revés. |

La oficina virtual tiene además sus propias alarmas de consumo (por ejemplo, un máximo de litros al día), que avisan por SMS. La integración no las lee ni las cambia; con **Consumo del último día** puedes crear las tuyas en Home Assistant.

## Instalación

La integración se instala desde el **Marketplace** de Home Assistant (**Ajustes > Marketplace**).

[![Abrir el repositorio en el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=miguelangel-nubla&repository=homeassistant_canal_isabel_II&category=integration)

1. Pulsa el botón y acepta añadir el repositorio. Si prefieres hacerlo a mano: abre el Marketplace, elige **Repositorios personalizados** en el menú de los tres puntos y añade `https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II` con la categoría **Integración**.
2. Descarga **Canal de Isabel II**.
3. Reinicia Home Assistant.

Hace falta Home Assistant 2026.11 o posterior.

Instalación manual: copia la carpeta `custom_components/canal_de_isabel_ii` de este repositorio en `config/custom_components/` y reinicia.

## Configuración

Son dos piezas: la integración, que guarda tus credenciales y descarga los datos, y el ayudante de sesión, que inicia sesión en la oficina virtual cuando la integración se lo pide.

1. Añade la integración y escribe tu número de documento (NIF o NIE), tu contraseña de la oficina virtual y el perfil con el que entras (normalmente **Particular**):

   [![Añadir la integración a Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=canal_de_isabel_ii)

   A mano: **Ajustes > Dispositivos y servicios > Añadir integración** y busca **Canal de Isabel II**.
2. Instala el ayudante de sesión siguiendo [su guía](canal-session-helper/DOCS.md). Como aplicación de Home Assistant (lo que antes se llamaba complemento) no hay nada que configurar; como contenedor Docker solo necesita la dirección de Home Assistant y un token.

En un minuto el ayudante inicia sesión y la integración descarga el último año de consumo. No hay nada más que hacer.

### Cómo funciona

- La integración lee los datos dos veces al día. La primera descarga trae el último año de consumo horario; las siguientes, los últimos 30 días, de modo que las horas que el Canal publica con retraso se rellenan solas.
- Cuando le toca leer y no tiene una sesión válida, lo anota. El ayudante pregunta cada minuto a Home Assistant si hay trabajo, inicia sesión con tus credenciales y entrega la sesión. La integración descarga los datos en ese momento.
- Entre lecturas no se hace nada en el portal: la sesión no se mantiene abierta, simplemente caduca.

### Cuándo tienes que intervenir

Solo cuando el ayudante no consigue entrar. Home Assistant te lo dice en **Ajustes**, sin que tengas que estar pendiente:

| Qué ha pasado | Qué ves en Home Assistant | Qué hacer |
|---------------|---------------------------|-----------|
| El portal rechaza tus credenciales | La integración pide volver a autenticarse | Escribe de nuevo el documento y la contraseña. |
| El portal pide resolver un captcha | Un aviso en **Reparaciones** con un enlace | Abre el navegador del ayudante e inicia sesión a mano, una vez. |
| El portal no responde o ha cambiado su página | Un aviso en **Reparaciones** | Esperar: el ayudante lo reintenta. Si se repite, abre su navegador para ver qué pasa. |
| El ayudante no está en marcha | Un aviso en **Reparaciones** | Arranca el ayudante. |

Los avisos desaparecen solos cuando vuelve a haber sesión. Los detalles (cuándo reintenta y por qué no insiste con una contraseña rechazada) están en la [guía del ayudante](canal-session-helper/DOCS.md).

Tus credenciales se guardan en Home Assistant, como las de cualquier otra integración, y solo se escriben en el formulario de la oficina virtual.

### Cambiar la cuenta o los ajustes

- **Documento, contraseña o perfil:** en [la página de la integración](https://my.home-assistant.io/redirect/integration/?domain=canal_de_isabel_ii), abre el menú de los tres puntos de la entrada y elige **Reconfigurar**. Hazlo cuando cambies la contraseña en la oficina virtual, sin esperar a que el portal la rechace.
- **Aviso de fuga:** los dos límites están en la sección **Configuración** del dispositivo de cada contrato (ver [Posible fuga](#posible-fuga)).
- **El ayudante** no tiene ajustes sobre tu cuenta.

### El captcha del portal: qué puede fallar

El formulario de acceso de la oficina virtual está protegido por un captcha invisible (reCAPTCHA). No pide nada a quien entra: observa cada inicio de sesión y decide por su cuenta si lo deja pasar, si muestra una prueba (elegir imágenes, por ejemplo) o si lo rechaza. El ayudante no lo resuelve ni lo esquiva. Inicia sesión en un navegador de verdad, desde tu casa y con tu cuenta, y hasta ahora eso basta para que pase.

Eso tiene dos consecuencias que conviene conocer:

- **Puede dejar de funcionar sin previo aviso.** El Canal puede endurecer el captcha, cambiar su formulario o empezar a pedir pruebas, y nadie fuera del Canal sabe con certeza qué tiene en cuenta para decidir. Si ocurre, la integración sigue en pie pero deja de recibir datos nuevos, y Home Assistant te avisa (ver [Cuándo tienes que intervenir](#cuándo-tienes-que-intervenir)).
- **Cuando pide una prueba, la tienes que resolver tú**, en el navegador del ayudante. Con una vez suele bastar para que vuelva a entrar solo.

Para darle las mejores opciones de que funcione sin que tengas que intervenir:

- **No uses la oficina virtual ni la app Canal Clientes a la vez que la integración.** La integración entra unas dos veces al día, y cada entrada dura un par de minutos. Varios inicios de sesión de la misma cuenta al mismo tiempo, desde sitios distintos, son justo lo que estos sistemas consideran sospechoso, y el portal puede además cerrar una sesión al abrirse otra. Si tienes que hacer una gestión en la web o en la app, hazla y deja pasar un rato; la integración lo reintenta sola.
- **Usa un solo ayudante por cuenta.** Dos ayudantes, o dos Home Assistant con la misma cuenta, duplican los inicios de sesión.
- **No lo fuerces.** Reiniciar el ayudante o recargar la integración una y otra vez para «probar» provoca inicios de sesión de más. Los datos llegan con un día de retraso de todos modos: no hay nada que ganar.
- **Si la contraseña es incorrecta, corrígela en cuanto te lo pida.** El ayudante deja de insistir tras tres rechazos para que no se bloquee la cuenta, pero los rechazos también cuentan en tu contra.
- **Si te pide pruebas a menudo**, entra a mano en el navegador del ayudante un par de veces: un navegador con historial de entradas resueltas por una persona suele recibir menos pruebas.

Nada de esto es una garantía. La integración depende de una página web que no está pensada para esto; si conoces una vía oficial para obtener los datos, [abre una issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).

## Panel de Energía

[![Abrir la configuración de Energía](https://my.home-assistant.io/badges/config_energy.svg)](https://my.home-assistant.io/redirect/config_energy/)

En la configuración del panel de Energía (**Ajustes > Paneles > Energía**), en **Consumo de agua**, pulsa **Añadir fuente de agua** y elige la estadística **Canal de Isabel II `<contrato>`**.

Cada importación continúa la serie guardada, así que volver a descargar las mismas horas no duplica ni descuadra nada.

> [!IMPORTANT]
> **Si actualizas desde 2026.11.9 o anterior:** las horas se guardaban una hora tarde. El Canal etiqueta cada hora con el momento en que termina (la fila «00» de hoy es la última hora de ayer) y la integración la tomaba por el momento en que empieza. Al actualizar, el histórico guardado se mueve una hora atrás él solo, una única vez; los litros y los totales no cambian, pero el reparto por días sí: la última hora de cada día vuelve a su día.
>
> **Si actualizas desde 2026.11.5 o anterior:** actualiza la integración y el ayudante a la vez. Home Assistant te pedirá el documento y la contraseña de la oficina virtual, que ahora se guardan en la integración; el histórico se conserva. El ayudante ya no tiene opciones propias (`document`, `password`, `CANAL_DOCUMENT`, `CANAL_PASSWORD`...) y pegar la cookie a mano ya no es una forma de configurar la integración.
>
> **Si actualizas desde una versión anterior a 2026.11:** el histórico ya no se guarda en el sensor `Canal de Isabel II Total`, que se elimina. Tienes que volver a elegir la fuente de agua en el panel de Energía. Las estadísticas antiguas de ese sensor se pueden borrar desde [**Herramientas para desarrolladores > Estadísticas**](https://my.home-assistant.io/redirect/tools_statistics/).

## Limitaciones conocidas

- Si la cuenta tiene varios contratos se leen todos, cada uno con su dispositivo, hasta un máximo de 20. No se ha podido probar con una cuenta real de varios contratos: si tienes una y algo no cuadra, [abre una issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).
- La noche del cambio de hora de otoño el portal publica una sola fila para las dos horas que se llaman 02:00. En Home Assistant esa fila queda en una hora y la siguiente aparece vacía.

## Referencia

### Diagnóstico

**Descargar diagnósticos**, en [la página de la integración](https://my.home-assistant.io/redirect/integration/?domain=canal_de_isabel_ii), muestra si hay una sesión pedida y desde cuándo, cuándo preguntó el ayudante por última vez y el historial de sesiones (cuándo se entregó cada una, cuántas lecturas sirvió y cuándo la rechazó el portal). Nunca incluye las credenciales ni la cookie.

### Servicios para el ayudante

La integración no llama al ayudante: es el ayudante quien llama a estos servicios, que solo admiten administradores. No hace falta usarlos a mano; se documentan para quien quiera sustituir el ayudante por otra herramienta.

| Servicio | Para qué |
|----------|----------|
| `canal_de_isabel_ii.session_request` | Devuelve las entradas que necesitan una sesión, con sus credenciales. Hay que llamarlo pidiendo la respuesta (`return_response`). |
| `canal_de_isabel_ii.set_session` | Entrega la cookie `JSESSIONID` de una sesión iniciada (`jsessionid`, y `entry_id` si hay más de una entrada). La integración la comprueba y descarga los datos. |
| `canal_de_isabel_ii.report_login` | Avisa de que el inicio de sesión no ha salido: `result` (`refused`, `challenge` o `failed`) y, opcionales, `detail`, `retry_at` y `helper_url`. |

## Desarrollo

Las pruebas, la instancia local de Home Assistant y la máquina virtual para probar el ayudante como aplicación están descritas en [`dev/README.md`](dev/README.md).

Si conoces una API oficial o una forma mejor de obtener los datos, abre una [issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).
