# Canal de Isabel II para Home Assistant

Integración que lleva a Home Assistant el consumo de agua de tu contrato del [Canal de Isabel II](https://oficinavirtual.canaldeisabelsegunda.es/) (Madrid): el consumo hora a hora, listo para el panel de Energía, y la lectura del contador.

El Canal no ofrece una API pública. Los datos se leen de la oficina virtual, y para entrar en ella hace falta un navegador de verdad, porque su formulario de acceso lleva un captcha. Por eso la integración trabaja con un **ayudante de sesión**: un navegador que se ejecuta en tu servidor e inicia sesión con tu documento y tu contraseña cada vez que la integración va a leer datos.

## Qué obtienes

El Canal publica los datos con medio día o un día de retraso, así que nada de esto es en tiempo real: describe el último día publicado.

Por cada contrato, en el dispositivo `Canal de Isabel II <contrato>`:

| Qué | Para qué |
|-----|----------|
| Estadística horaria `canal_de_isabel_ii:consumption_<contrato>` | Histórico de consumo en litros, hora a hora. Es la que se añade al panel de Energía. |
| **Lectura del contador** | Lectura absoluta en m³, la cifra que aparece en la factura. |
| **Consumo del último día** | Litros del último día que el Canal ha publicado completo. La fecha va en el atributo `date`. |
| **Caudal mínimo del último día** | Los litros de la hora más tranquila de ese día. En una casa sin fugas es 0. |
| **Posible fuga** | Se activa cuando el contador no ha descansado ni una hora en las últimas 48 horas publicadas. |
| **Datos hasta** | Hasta qué hora ha publicado datos el Canal. Sirve para saber si están al día. |
| **Consumo de la última hora** | Litros de la última hora publicada. Desactivado por defecto: esa hora ya pasó hace mucho cuando se publica. |

### Posible fuga

En una casa siempre hay alguna hora del día, normalmente de madrugada, en la que no se gasta nada. Se cuenta como hora de descanso la que no llega a 1 litro, porque los contadores apuntan unas centésimas de litro en muchas horas en las que no hay nada abierto. Un contador que no descansa durante dos días seguidos suele ser una cisterna o un grifo que gotea, o una fuga después del contador. Como los datos llegan con un día de retraso, sirve para las fugas que duran, no para una rotura. Un riego por goteo, un descalcificador o una casa en la que se usa agua a todas horas también lo activan.

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

## Panel de Energía

[![Abrir la configuración de Energía](https://my.home-assistant.io/badges/config_energy.svg)](https://my.home-assistant.io/redirect/config_energy/)

En la configuración del panel de Energía (**Ajustes > Paneles > Energía**), en **Consumo de agua**, pulsa **Añadir fuente de agua** y elige la estadística **Canal de Isabel II `<contrato>`**.

Cada importación continúa la serie guardada, así que volver a descargar las mismas horas no duplica ni descuadra nada.

> [!IMPORTANT]
> **Si actualizas desde 2026.11.5 o anterior:** actualiza la integración y el ayudante a la vez. Home Assistant te pedirá el documento y la contraseña de la oficina virtual, que ahora se guardan en la integración; el histórico se conserva. El ayudante ya no tiene opciones propias (`document`, `password`, `CANAL_DOCUMENT`, `CANAL_PASSWORD`...) y pegar la cookie a mano ya no es una forma de configurar la integración.
>
> **Si actualizas desde una versión anterior a 2026.11:** el histórico ya no se guarda en el sensor `Canal de Isabel II Total`, que se elimina. Tienes que volver a elegir la fuente de agua en el panel de Energía. Las estadísticas antiguas de ese sensor se pueden borrar desde [**Herramientas para desarrolladores > Estadísticas**](https://my.home-assistant.io/redirect/tools_statistics/).

## Limitaciones conocidas

- Si la cuenta tiene varios contratos, solo se lee el que el portal muestra seleccionado.
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
