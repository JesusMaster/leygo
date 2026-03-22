# Catálogo de Tareas Repetitivas

A continuación se documentan los flujos y automatizaciones recurrentes solicitadas por el usuario:

## Generación de Imágenes con Nanobanana
- **Descripción**: Creación de imágenes a partir de ideas o prompts del usuario utilizando el modelo `gemini-3-pro-image-preview`.
- **Agente Responsable**: `nanobanana`
- **Flujo**:
  1. El usuario solicita generar una imagen dando una idea.
  2. El agente `nanobanana` recibe la idea, la optimiza si es necesario para crear un buen prompt visual.
  3. El agente ejecuta su herramienta interna `generar_imagen_nanobanana` que llama a la API de Gemini para generar la imagen en formato 1:1 (1024x1024 px).
  4. La imagen se guarda en `agent_core/sub_agents/nanobanana/files/` y se le notifica al usuario la ruta de la imagen generada.