# Bitácora de Lecciones Aprendidas y Autocorrecciones

Este archivo funciona como un registro permanente de problemas difíciles que he logrado resolver, errores que he cometido previamente y las estrategias correctas descubiertas para evitar tropezar con la misma piedra en el futuro.

## Registro:


### Generación de Imágenes con Gemini 3.1 Flash Image Preview
- **Problema**: Al intentar usar el modelo `gemini-3.1-flash-image-preview` con el SDK de `google-genai` usando `client.models.generate_images`, se obtenía un error `404 NOT_FOUND` indicando que el modelo no estaba soportado para `predict` en `v1beta`.
- **Solución**: Este modelo no usa el endpoint `predict` (como los modelos Imagen 3), sino el endpoint estándar `generateContent`. Además, requiere la versión `v1alpha` de la API y configurar `responseModalities: ["IMAGE"]` en el `generationConfig`. Para evitar problemas de compatibilidad con versiones del SDK, es más seguro hacer la petición HTTP directa a `https://generativelanguage.googleapis.com/v1alpha/models/gemini-3.1-flash-image-preview:generateContent` y decodificar el `inlineData` en base64 de la respuesta.


### Renderizado de Imágenes en el Chat (Corrección)
- **Problema**: Las interfaces de chat web o de terminal a menudo no pueden renderizar imágenes usando rutas locales relativas (`![alt](ruta/local.jpg)`) por razones de seguridad o falta de un servidor de archivos estáticos.
- **Solución**: Se actualizó el agente `nanobanana` para que, tras guardar la imagen localmente, la suba automáticamente a un servicio de hosting de imágenes temporal y gratuito (como `catbox.moe` vía API anónima). De esta forma, el agente devuelve una URL pública (`![alt](https://files.catbox.moe/...)`) que cualquier interfaz Markdown estándar puede renderizar sin problemas, manteniendo el historial limpio sin usar base64.