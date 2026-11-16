# Canal de Isabel II para Home Assistant

Integración que lleva a Home Assistant el consumo de agua de tu contrato del [Canal de Isabel II](https://oficinavirtual.canaldeisabelsegunda.es/) (Madrid): el consumo hora a hora, listo para el panel de Energía, y la lectura del contador.

El Canal no ofrece una API pública. La integración lee los datos de la oficina virtual con la sesión de un navegador en el que tú has iniciado sesión.

## Qué obtienes

Por cada contrato:

| Qué | Dónde | Para qué |
|-----|---------------|----------|
| Estadística horaria | `canal_de_isabel_ii:consumption_<contrato>` | Histórico de consumo en litros. Es la que se añade al panel de Energía. |
| Sensor **Consumo** | en el dispositivo `Canal de Isabel II <contrato>` | Litros de la última hora publicada por el Canal. |
| Sensor **Lectura del contador** | en el mismo dispositivo | Lectura absoluta en m³, la cifra que aparece en la factura. |

El Canal publica los datos con medio día o un día de retraso, así que no es un contador en tiempo real.

## Instalación

La integración se instala desde el **Marketplace** de Home Assistant (**Ajustes > Marketplace**).

[![Abrir el repositorio en el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=miguelangel-nubla&repository=homeassistant_canal_isabel_II&category=integration)

1. Pulsa el botón, o abre el Marketplace, elige **Repositorios personalizados** en el menú de los tres puntos y añade `https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II` con la categoría **Integración**.
2. Busca **Canal de Isabel II** y descárgala.
3. Reinicia Home Assistant.

Instalación manual: copia la carpeta `custom_components/canal_de_isabel_ii` de este repositorio en `config/custom_components/` y reinicia.

## Configuración

La integración necesita la sesión de un navegador que haya iniciado sesión en la oficina virtual. El portal la cierra cada cierto tiempo (no documenta cuándo), así que lo cómodo es que algo la mantenga y te avise cuando haya que volver a entrar. De eso se encarga el ayudante de sesión.

En ningún caso se guardan ni se envían tu usuario y tu contraseña: el inicio de sesión lo haces siempre tú.

### Con el ayudante de sesión (recomendado)

El ayudante es un navegador que se ejecuta como complemento de Home Assistant o como contenedor Docker en tu servidor.

1. Instala el ayudante siguiendo [su guía](canal-session-helper/DOCS.md).
2. En Home Assistant, ve a **Ajustes > Dispositivos y servicios > Añadir integración**, busca **Canal de Isabel II** y deja el campo de la cookie vacío.
3. Abre el ayudante e inicia sesión en la oficina virtual.

El ayudante entrega la sesión a la integración, la mantiene viva y crea una notificación en Home Assistant cuando el portal la cierra y hay que volver a iniciar sesión.

### A mano

1. Inicia sesión en la [oficina virtual](https://oficinavirtual.canaldeisabelsegunda.es/) con tu navegador.
2. Abre las herramientas de desarrollador (F12) y ve a **Aplicación > Cookies** (*Almacenamiento > Cookies* en Firefox).
3. Copia el valor de la cookie `JSESSIONID`.
4. Añade la integración como en el paso 2 de arriba y pega el valor.

Cuando el portal cierre la sesión, Home Assistant te pedirá una nueva: repite los pasos y pégala en el aviso.

### Qué se descarga

La primera descarga trae el último año de consumo horario. Después la integración vuelve a leer los últimos 30 días dos veces al día, de modo que las horas publicadas con retraso se rellenan solas. Entre descargas comprueba la sesión cada 10 minutos para mantenerla viva.

## Panel de Energía

**Ajustes > Paneles > Energía > Consumo de agua > Añadir fuente de agua** y elige la estadística **Canal de Isabel II `<contrato>`**.

Cada importación continúa la serie guardada, así que volver a descargar las mismas horas no duplica ni descuadra nada.

> [!IMPORTANT]
> **Si actualizas desde una versión anterior a 2026.11:** el histórico ya no se guarda en el sensor `Canal de Isabel II Total`, que se elimina. Tienes que volver a elegir la fuente de agua en el panel de Energía. Las estadísticas antiguas de ese sensor se pueden borrar desde **Herramientas para desarrolladores > Estadísticas**.

## Limitaciones conocidas

- Si la cuenta tiene varios contratos, solo se lee el que el portal muestra seleccionado.
- La noche del cambio de hora de otoño el portal publica una sola fila para las dos horas que se llaman 02:00. En Home Assistant esa fila queda en una hora y la siguiente aparece vacía.

## Referencia

### Servicio `canal_de_isabel_ii.set_session`

Recibe una cookie `JSESSIONID`, la comprueba con el portal, la guarda e importa los datos al momento. Solo lo pueden llamar administradores. Es lo que usa el ayudante de sesión, y sirve para cualquier otra herramienta que obtenga la sesión fuera de Home Assistant.

| Campo | |
|-------|---|
| `jsessionid` | Valor de la cookie. |
| `entry_id` | Opcional. Solo si la integración está añadida más de una vez. |

### Diagnóstico de la sesión

La integración registra cuánto dura cada sesión: cuándo se configuró, la última comprobación correcta y el momento en que el portal la rechazó. Se consulta con **Descargar diagnósticos** en la página de la integración. La cookie nunca se incluye.

## Desarrollo

Las pruebas, la instancia local de Home Assistant y la máquina virtual para probar el complemento están descritas en [`dev/README.md`](dev/README.md).

Si conoces una API oficial o una forma mejor de obtener los datos, abre una [issue](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II/issues).
