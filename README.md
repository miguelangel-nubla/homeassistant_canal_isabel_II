# Canal de Isabel II para Home Assistant

Componente para integrar los datos de consumo de agua del Canal de Isabel II en Home Assistant.

## Características

-   Descarga el consumo horario de agua.
-   Importa el histórico como estadística de Home Assistant, lista para el panel de Energía.
-   Crea sensores con el último consumo horario y la lectura del contador.

## Instalación

### Marketplace de Home Assistant (recomendado)

Desde Home Assistant 2026.11, HACS viene integrado como **Marketplace** (**Ajustes > Marketplace**). En versiones anteriores los mismos pasos se hacen desde HACS.

[![Abrir el repositorio en el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=miguelangel-nubla&repository=homeassistant_canal_isabel_II&category=integration)

1.  Pulsa el botón de arriba, o abre el Marketplace, elige **Repositorios personalizados** en el menú de los tres puntos y añade `https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II` con la categoría **Integración**.
2.  Busca **Canal de Isabel II** y descárgala.
3.  Reinicia Home Assistant.

### Instalación Manual

1.  Descarga la carpeta `custom_components/canal_de_isabel_ii` de este repositorio.
2.  Cópiala en tu carpeta `config/custom_components/`.
3.  Reinicia Home Assistant.

## Configuración

1.  Ve a **Ajustes > Dispositivos y Servicios**.
2.  Dale a **Añadir integración**.
3.  Busca **Canal de Isabel II**.
4.  Te pedirá el `JSESSIONID`. Para sacarlo:
    1.  Entra en la [oficina virtual](https://oficinavirtual.canaldeisabelsegunda.es/) con tu navegador e inicia sesión.
    2.  Pulsa F12 para abrir la consola de desarrollador.
    3.  Ve a la pestaña **Aplicación** > **Cookies** (o *Storage > Cookies* según el navegador).
    4.  Busca la cookie llamada `JSESSIONID` y copia su valor.

> [!WARNING]
> **Caducidad de la sesión:** `JSESSIONID` es una cookie de sesión temporal emitida por el servidor web del Canal de Isabel II y **caduca aproximadamente cada hora** (o cuando se cierra la sesión en la web). Cuando caduque, Home Assistant te pedirá re-autenticarte introduciendo la nueva cookie.

## Datos y panel de Energía

Por cada contrato se crean:

| Qué | Identificador | Para qué |
|-----|---------------|----------|
| Estadística horaria | `canal_de_isabel_ii:consumption_<contrato>` | Histórico de consumo en litros. Es la que se añade al panel de Energía. |
| Sensor de último consumo | `sensor.canal_de_isabel_ii_<contrato>_consumption` (en instalaciones anteriores conserva su identificador) | Litros de la última hora publicada por el Canal. |
| Sensor de lectura del contador | `sensor.canal_de_isabel_ii_<contrato>_meter_reading` | Lectura absoluta en m³, la cifra que aparece en la factura. |

Para añadirlo al panel de Energía: **Ajustes > Paneles > Energía > Consumo de agua > Añadir fuente de agua** y elige la estadística **Canal de Isabel II `<contrato>`**.

Cada importación continúa la serie guardada, así que volver a descargar las mismas horas no duplica ni descuadra nada.

La primera descarga pide el último año completo de consumo horario; las siguientes, los últimos 30 días, de modo que las horas publicadas con retraso o una temporada sin sesión se rellenan solas.

Limitaciones conocidas:

- Si la cuenta tiene varios contratos, solo se lee el que el portal muestra seleccionado.
- La noche del cambio de hora de otoño el portal publica una sola fila para las dos horas que se llaman 02:00. En Home Assistant esa fila queda en una hora y la siguiente aparece vacía.

> [!IMPORTANT]
> **Si actualizas desde una versión anterior:** el histórico ya no se guarda en el sensor `Canal de Isabel II Total`, que se elimina. Tienes que volver a elegir la fuente de agua en el panel de Energía. Las estadísticas antiguas de ese sensor se pueden borrar desde **Herramientas para desarrolladores > Estadísticas**.

## Entregar la sesión sin la interfaz

El servicio `canal_de_isabel_ii.set_session` recibe una cookie `JSESSIONID`, la valida, la guarda e importa los datos al momento. Sirve para que otra herramienta entregue la sesión en lugar de pegarla en el formulario de reautenticación.

La carpeta [`canal-session-helper`](canal-session-helper/) contiene un contenedor opcional que lo usa: un navegador en tu servidor en el que inicias sesión tú, y que a partir de ahí entrega y vigila la sesión. También se puede instalar como complemento (add-on) de Home Assistant.

## Diagnóstico de la sesión

La integración registra cuánto dura cada sesión: cuándo se configuró, la última comprobación correcta y el momento en que el portal la rechazó. Se puede consultar con **Descargar diagnósticos** en la página de la integración. La cookie nunca se incluye.

> [!NOTE]
> Dada la web actual del Canal de Isabel II y la interfaz que utiliza, actualmente se requiere este método manual. Tampoco hay API pública conocida. Si alguien conoce una alternativa mejor o es capaz de obtener una API oficial/login automático, por favor házmelo saber abriendo una issue.