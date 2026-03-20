
# Instrucciones de Code Review
1. Cuando revises una Pull Request, primero obtén los archivos modificados usando `get_pull_request_files`.
2. Para cada archivo de código fuente modificado, usa `analizar_seguridad_codigo` y `verificar_estandares_codigo` para detectar problemas.
3. Usa `verificar_cobertura_pruebas` pasándole la lista de archivos modificados para asegurarte de que se incluyeron tests.
4. Si te piden generar un resumen o changelog, usa `list_commits` para obtener los mensajes y luego pásalos a `generar_resumen_changelog`.
5. Finalmente, agrupa todos tus hallazgos y usa `create_pull_request_review` o `add_pull_request_review_comment` para dejar tu feedback en GitHub.