# Ayudante de sesión del Canal de Isabel II

Un navegador que se ejecuta en tu servidor para la integración [Canal de Isabel II](https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II) de Home Assistant. Cuando la integración va a leer tu consumo, el ayudante inicia sesión en la oficina virtual con las credenciales que le da la integración y le entrega la sesión. El resto del tiempo no hace nada.

No tiene nada que configurar sobre tu cuenta: el documento y la contraseña se escriben al añadir la integración. Solo hay que abrir su navegador si el portal pide resolver un captcha.

Se puede usar como aplicación de Home Assistant (lo que antes se llamaba complemento) o como contenedor Docker. Las instrucciones de ambos están en [DOCS.md](DOCS.md).
