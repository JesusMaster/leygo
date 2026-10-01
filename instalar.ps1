# Instala o actualiza leygo con Docker en Windows (Docker Desktop con WSL 2).
#
#   .\instalar.ps1                     solo leygo (usa tu Redis, Qdrant y Ollama)
#   .\instalar.ps1 -Redis -Qdrant      además levanta Redis y Qdrant dentro de Docker
#   .\instalar.ps1 -Todo               Redis + Qdrant + Ollama en Docker
#
# Opciones (también valen como --redis, --puerto 8080, etc.):
#   -Redis         Redis en Docker (sesiones y conversaciones)
#   -Qdrant        Qdrant en Docker (memoria vectorial)
#   -Ollama        Ollama en Docker (modelos y embeddings locales)
#   -Todo          los tres
#   -Ninguno       ninguno en Docker (usa los tuyos o servicios en la nube)
#   -Dominio X     dominio para Caddy (por defecto :80, http://localhost sin TLS)
#   -Puerto N      puerto de la interfaz en tu computador (por defecto 80: http://localhost:N)
#   -Version X     versión de leygo a instalar (por defecto la última; queda en .env)
#   -SinBuild      no reconstruye ni descarga las imágenes
#
# En Windows no hay botón "Actualizar" en la interfaz (el servicio actualizador no funciona con
# rutas C:\): para actualizar, corre .\instalar.ps1 de nuevo.
#
# Si Windows no deja correr scripts:  powershell -ExecutionPolicy Bypass -File .\instalar.ps1
#
# La selección queda en .env (COMPOSE_PROFILES): .\instalar.ps1 sin opciones (o docker compose up -d)
# vuelve a levantar lo mismo. Para cambiarla, córrelo con otras opciones.
#
# Varios leygo en el mismo computador: cada uno en su carpeta y con su puerto
# (.\instalar.ps1 -Puerto 8080). Cada carpeta es un proyecto de Docker aparte, con sus datos.

#Requires -Version 5.1
[CmdletBinding(PositionalBinding = $false)]
param(
  [switch]$Redis,
  [switch]$Qdrant,
  [switch]$Ollama,
  [switch]$Todo,
  [switch]$Ninguno,
  [string]$Dominio = '',
  [string]$Puerto = '',
  [string]$Version = '',
  [switch]$SinBuild,
  [switch]$Ayuda,
  # Lo que no es un parámetro de arriba: la forma --redis, --puerto 8080, -h, …
  [Parameter(ValueFromRemainingArguments = $true)][object[]]$Resto
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # la barra de progreso hace lentísimo Invoke-WebRequest en 5.1
$EsWindows = $env:OS -eq 'Windows_NT'
$Utf8SinBom = New-Object System.Text.UTF8Encoding $false
$Aqui = $PSScriptRoot
$ArchivoEnv = Join-Path $Aqui '.env'

# ─── .env ──────────────────────────────────────────────────────────────────
# docker compose lee .env: se escribe en UTF-8 sin BOM y con saltos LF, sin importar cómo vino.
function Leer-LineasEnv {
  if (-not (Test-Path -LiteralPath $ArchivoEnv)) { return ,@() }
  $t = [IO.File]::ReadAllText($ArchivoEnv, $Utf8SinBom).TrimStart([char]0xFEFF) -replace "`r`n", "`n" -replace "`r", "`n"
  if ($t.EndsWith("`n")) { $t = $t.Substring(0, $t.Length - 1) }
  if ($t -eq '') { return ,@() }
  return ,($t -split "`n")
}
function Escribir-LineasEnv([string[]]$lineas) {
  [IO.File]::WriteAllText($ArchivoEnv, (($lineas -join "`n") + "`n"), $Utf8SinBom)
}
# Valor de la variable (la última si se repite), sin comentario al final ni comillas.
function Leer([string]$k) {
  $v = $null
  foreach ($l in (Leer-LineasEnv)) { if ($l.StartsWith("$k=")) { $v = $l.Substring($k.Length + 1) } }
  if ($null -eq $v) { return '' }
  return ($v -replace '\s*#.*$', '' -replace "^['`"]", '' -replace "['`"]$", '')
}
# Cambia la primera línea de la variable o la agrega al final. El resto del archivo queda igual.
function Poner([string]$k, [string]$v) {
  $lineas = New-Object System.Collections.Generic.List[string]
  $hecho = $false
  foreach ($l in (Leer-LineasEnv)) {
    if (-not $hecho -and $l.StartsWith("$k=")) { $lineas.Add("$k=$v"); $hecho = $true } else { $lineas.Add($l) }
  }
  if (-not $hecho) { $lineas.Add("$k=$v") }
  Escribir-LineasEnv $lineas.ToArray()
}
# Saca \r y BOM si alguien editó .env con un editor de Windows.
function Normalizar-Env {
  if (-not (Test-Path -LiteralPath $ArchivoEnv)) { return }
  $b = [IO.File]::ReadAllBytes($ArchivoEnv)
  $bom = $b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF
  if ($bom -or ($b -contains 13)) { Escribir-LineasEnv (Leer-LineasEnv) }
}
# .env tiene claves: solo tu usuario lo puede leer (como chmod 600).
function Proteger-Archivo([string]$f) {
  $ErrorActionPreference = 'Continue'
  try {
    if ($EsWindows) {
      $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
      & icacls.exe $f /inheritance:r /grant:r "*${sid}:F" 2>$null | Out-Null
    } else { & chmod 600 $f 2>$null }
  } catch { }
}

# Dentro de Docker "localhost" es el propio contenedor: tu computador es host.docker.internal.
function Local-A-Host([string]$s) { return ([regex]'(localhost|127\.0\.0\.1)').Replace($s, 'host.docker.internal', 1) }
function Es-Local([string]$s) { return $s -match '(^|//)(localhost|127\.0\.0\.1)(:|/|$)' }
# Apunta al servicio de Docker de leygo (que se apaga si no se elige).
function Es-Docker([string]$s, [string]$servicio) { return $s -match "^(https?://)?$servicio(:|/|$)" }

# Corre docker y devuelve lo que escribe, sin cortar el script si falla ($LASTEXITCODE dice cómo le fue).
# La salida de docker viene en UTF-8: sin esto Windows PowerShell la lee con la página de códigos de la consola.
function Docker-Texto {
  $ErrorActionPreference = 'Continue'
  $antes = $null
  try { $antes = [Console]::OutputEncoding; [Console]::OutputEncoding = $Utf8SinBom } catch { }
  try { return ((& docker @args 2>$null) | Out-String) }
  finally { if ($antes) { try { [Console]::OutputEncoding = $antes } catch { } } }
}

# Corre docker mostrando su salida en la consola. docker escribe el progreso por stderr: en Windows
# PowerShell, con la salida redirigida, eso llega como error y con 'Stop' cortaría el script.
function Docker-Consola {
  $ErrorActionPreference = 'Continue'
  & docker @args
}

function Mostrar-Ayuda {
  foreach ($l in (Get-Content -LiteralPath $PSCommandPath -Encoding UTF8)) {
    if ($l -notmatch '^#') { break }
    Write-Host ($l -replace '^# ?', '')
  }
}

function Salir([int]$codigo) { Pop-Location; exit $codigo }

Push-Location -LiteralPath $Aqui
# Cualquier error inesperado: mensaje corto y la consola vuelve a la carpeta donde estabas.
trap { Write-Host "✗ $_"; Salir 1 }

# ─── Archivos de instalación al día ───────────────────────────────────────────
# Instalación descargada (sin Dockerfile): antes de nada trae la última versión de los archivos de
# instalación (docker-compose.yml, Caddyfile y este mismo script). Tus datos, tu .env y tu config/
# no se tocan. LEYGO_SIN_DESCARGA=1 lo salta (lo usa el instalador de leygo.cl, que ya bajó todo).
$Fuente = if ($env:LEYGO_FUENTE) { $env:LEYGO_FUENTE.TrimEnd('/') } else { 'https://raw.githubusercontent.com/JesusMaster/leygo/main' }
if (-not (Test-Path -LiteralPath (Join-Path $Aqui 'Dockerfile')) -and -not $env:LEYGO_SIN_DESCARGA) {
  Write-Host 'Revisando los archivos de instalación…'
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
  New-Item -ItemType Directory -Force -Path (Join-Path $Aqui 'deploy') | Out-Null
  $faltaron = @()
  foreach ($f in 'docker-compose.yml', 'deploy/Caddyfile', 'deploy/actualizador.sh', '.env.example', 'LICENCIA.txt', 'README.md', 'instalar.sh') {
    $destino = Join-Path $Aqui $f
    try {
      Invoke-WebRequest -UseBasicParsing -Uri "$Fuente/$f" -OutFile "$destino.tmp"
      Move-Item -LiteralPath "$destino.tmp" -Destination $destino -Force
    } catch {
      Remove-Item -LiteralPath "$destino.tmp" -Force -ErrorAction SilentlyContinue
      $faltaron += $f
    }
  }
  if ($faltaron.Count) { Write-Host "  ! No se pudieron bajar: $($faltaron -join ' ') (sigo con los que tienes)." }

  $nuevo = Join-Path $Aqui 'instalar.ps1.nuevo'
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "$Fuente/instalar.ps1" -OutFile $nuevo
    if ((Get-Item -LiteralPath $nuevo).Length -gt 0 -and
        (Get-FileHash -LiteralPath $nuevo).Hash -ne (Get-FileHash -LiteralPath $PSCommandPath).Hash) {
      Move-Item -LiteralPath $nuevo -Destination $PSCommandPath -Force
      Write-Host '  • instalar.ps1 actualizado: sigo con la versión nueva.'
      # Mismas opciones, sin volver a descargar. La variable se borra al terminar: si no, quedaría
      # en tu consola y el próximo .\instalar.ps1 no revisaría los archivos.
      $env:LEYGO_SIN_DESCARGA = '1'
      $opciones = @{}; foreach ($k in $PSBoundParameters.Keys) { $opciones[$k] = $PSBoundParameters[$k] }
      try { & $PSCommandPath @opciones; $codigo = $LASTEXITCODE } finally { Remove-Item Env:LEYGO_SIN_DESCARGA -ErrorAction SilentlyContinue }
      Salir $codigo
    }
  } catch { }
  Remove-Item -LiteralPath $nuevo -Force -ErrorAction SilentlyContinue
}

# ─── Opciones ─────────────────────────────────────────────────────────────────
$build = -not $SinBuild
$eligio = $Redis -or $Qdrant -or $Ollama -or $Todo -or $Ninguno
$usaRedis = [bool]($Redis -or $Todo); $usaQdrant = [bool]($Qdrant -or $Todo); $usaOllama = [bool]($Ollama -or $Todo)
$dominio = $Dominio; $puerto = $Puerto; $version = $Version

# La forma de la documentación de Mac y Linux: --redis, --puerto 8080, --puerto=8080, …
$resto = @(if ($Resto) { $Resto | ForEach-Object { "$_" } })
$sinValor = { param($op) Write-Host "Falta el valor de $op (por ejemplo $op 8080)."; Salir 1 }
for ($i = 0; $i -lt $resto.Count; $i++) {
  $a = $resto[$i]
  switch -regex ($a) {
    '^--redis$'   { $usaRedis = $true; $eligio = $true; break }
    '^--qdrant$'  { $usaQdrant = $true; $eligio = $true; break }
    '^--ollama$'  { $usaOllama = $true; $eligio = $true; break }
    '^--(todo|local)$' { $usaRedis = $true; $usaQdrant = $true; $usaOllama = $true; $eligio = $true; break }
    '^--ninguno$' { $eligio = $true; break }
    '^--sin-build$' { $build = $false; break }
    # El actualizador no corre en Windows: se aceptan para que los comandos de Mac y Linux no fallen.
    '^-(-sin-actualizador|-con-actualizador|SinActualizador|ConActualizador)$' { break }
    '^--(dominio|puerto|version)$' {
      if ($i + 1 -ge $resto.Count) { & $sinValor $a }
      $i++; $v = $resto[$i]
      switch ($a) { '--dominio' { $dominio = $v } '--puerto' { $puerto = $v } '--version' { $version = $v } }
      break
    }
    '^--(dominio|puerto|version)=' {
      $v = $a.Substring($a.IndexOf('=') + 1)
      switch -regex ($a) { '^--dominio' { $dominio = $v } '^--puerto' { $puerto = $v } '^--version' { $version = $v } }
      break
    }
    '^(-h|--help|-help|--ayuda|/\?)$' { Mostrar-Ayuda; Salir 0 }
    default { Write-Host "Opción desconocida: $a (usa -Ayuda)"; Salir 1 }
  }
}
if ($Ayuda) { Mostrar-Ayuda; Salir 0 }

# ─── Docker ───────────────────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host 'Falta Docker: instala Docker Desktop con WSL 2 (https://docs.docker.com/desktop/setup/install/windows-install/),'
  Write-Host 'ábrelo y vuelve a correr este comando.'
  Salir 1
}
Docker-Texto compose version | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "Falta 'docker compose' (viene con Docker Desktop: actualízalo desde https://docs.docker.com/desktop/setup/install/windows-install/)."; Salir 1 }
Docker-Texto info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host 'Docker no está corriendo: abre Docker Desktop, espera a que diga que está listo y vuelve a correr .\instalar.ps1'; Salir 1 }

function Es-Puerto([string]$n) { return $n -match '^[0-9]{1,5}$' -and [int]$n -ge 1 -and [int]$n -le 65535 }
if ($puerto -ne '' -and -not (Es-Puerto $puerto)) { Write-Host 'El puerto debe ser un número entre 1 y 65535 (por ejemplo -Puerto 8080).'; Salir 1 }

if (-not (Test-Path -LiteralPath $ArchivoEnv)) {
  Copy-Item -LiteralPath (Join-Path $Aqui '.env.example') -Destination $ArchivoEnv
  Proteger-Archivo $ArchivoEnv
  Write-Host '✓ .env creado desde .env.example'
}
Normalizar-Env
New-Item -ItemType Directory -Force -Path (Join-Path $Aqui 'data'), (Join-Path $Aqui 'config') | Out-Null

# Sin opciones de servicios: se repite la selección anterior.
if (-not $eligio -and ((Leer-LineasEnv) -match '^COMPOSE_PROFILES=')) {
  $prev = ",$(Leer COMPOSE_PROFILES),"
  if ($prev -match ',(redis|local),') { $usaRedis = $true }
  if ($prev -match ',(qdrant|local),') { $usaQdrant = $true }
  if ($prev -match ',(ollama|local),') { $usaOllama = $true }
  $antes = Leer COMPOSE_PROFILES; if ($antes -eq '') { $antes = 'ninguno en Docker' }
  Write-Host "Misma selección que la vez anterior ($antes). Cámbiala con -Redis, -Qdrant, -Ollama, -Todo o -Ninguno."
}

$perfiles = @()
Write-Host ''
Write-Host 'Servicios:'

if ($usaRedis) {
  $perfiles += 'redis'
  $h = Leer REDIS_HOST
  if ($h -eq '' -or (Es-Local $h)) { Poner REDIS_HOST redis; Poner REDIS_PORT 6379 }
  Write-Host '  • Redis   → en Docker (redis:6379)'
} else {
  $h = Leer REDIS_HOST
  if (Es-Docker $h redis) { Write-Host '  ! Redis de Docker queda apagado (sus datos siguen en el volumen). Apunto a tu computador.' }
  if ($h -eq '' -or (Es-Local $h) -or (Es-Docker $h redis)) { Poner REDIS_HOST host.docker.internal; $h = 'host.docker.internal' }
  Write-Host "  • Redis   → el tuyo (${h}:$(Leer REDIS_PORT))"
}

if ($usaQdrant) {
  $perfiles += 'qdrant'
  $u = Leer QDRANT_URL
  if ($u -eq '' -or (Es-Local $u)) { Poner QDRANT_URL 'http://qdrant:6333' }
  Write-Host '  • Qdrant  → en Docker (http://qdrant:6333)'
} else {
  $u = Leer QDRANT_URL; if ($u -eq '') { $u = 'http://localhost:6333' }
  if (Es-Docker $u qdrant) { Write-Host '  ! Qdrant de Docker queda apagado (sus datos siguen en el volumen). Apunto a tu computador.'; $u = 'http://host.docker.internal:6333'; Poner QDRANT_URL $u }
  if (Es-Local $u) { $u = Local-A-Host $u; Poner QDRANT_URL $u }
  Write-Host "  • Qdrant  → el tuyo ($u)"
}

if ($usaOllama) {
  $perfiles += 'ollama'
  $u = Leer OLLAMA_BASE_URL
  if ($u -eq '' -or (Es-Local $u)) { Poner OLLAMA_BASE_URL 'http://ollama:11434' }
  Write-Host '  • Ollama  → en Docker (http://ollama:11434)'
} else {
  $u = Leer OLLAMA_BASE_URL; if ($u -eq '') { $u = 'http://localhost:11434' }
  if (Es-Docker $u ollama) { $u = 'http://host.docker.internal:11434'; Poner OLLAMA_BASE_URL $u }
  if (Es-Local $u) { $u = Local-A-Host $u; Poner OLLAMA_BASE_URL $u }
  Write-Host "  • Ollama  → el tuyo o un proveedor de pago para embeddings ($u)"
}

# El botón "Actualizar" usa el servicio actualizador, que monta esta carpeta en la misma ruta dentro
# del contenedor: con rutas C:\ no funciona. En Windows se actualiza corriendo .\instalar.ps1.
if (-not (Test-Path -LiteralPath (Join-Path $Aqui 'Dockerfile'))) {
  Write-Host '  • Actualizador → no disponible en Windows (actualiza con .\instalar.ps1)'
}

Poner COMPOSE_PROFILES ($perfiles -join ',')

# Lo que guardó el asistente (data/env.gui) tiene prioridad sobre .env.
$envGui = Join-Path $Aqui 'data/env.gui'
$textoGui = if (Test-Path -LiteralPath $envGui) { [IO.File]::ReadAllText($envGui) } else { '' }
if ($textoGui -match '(?m)^(REDIS_HOST|QDRANT_URL|OLLAMA_BASE_URL)=') {
  Write-Host '  ! El asistente ya guardó conexiones en data/env.gui y esas mandan. Si cambiaste de servicios, ajústalas en Ajustes → Asistente de configuración.'
}

if ($dominio -ne '') { Poner DOMAIN $dominio }
elseif ((Leer DOMAIN) -eq '') { Poner DOMAIN ':80' }
# Dentro del contenedor Caddy siempre escucha en 80/443; el puerto elegido es el de tu computador.
$esLocal = (Leer DOMAIN).StartsWith(':')
if ($esLocal) { Poner DOMAIN ':80' }

# Nombre del proyecto de Docker: el de la carpeta. Si ya hay otro leygo con ese nombre en otra
# carpeta, se le agrega un sufijo para que no compartan contenedores ni volúmenes.
if ((Leer COMPOSE_PROJECT_NAME) -eq '') {
  $base = ((Split-Path -Leaf $Aqui).ToLowerInvariant() -replace '[^a-z0-9_-]', '')
  if ($base -eq '') { $base = 'leygo' }
  $nombre = $base
  $json = Docker-Texto compose ls -a --filter "name=^$base$" --format json
  $proyectos = @()
  try { if ($json.Trim()) { $proyectos = @($json | ConvertFrom-Json | ForEach-Object { $_ }) } } catch { }
  $otro = @($proyectos | Where-Object { $_.Name -eq $base })
  if ($otro.Count) {
    $esEste = $false
    foreach ($proy in $otro) {
      foreach ($c in ("$($proy.ConfigFiles)" -split ',')) {
        if ($c.Trim().StartsWith("$Aqui\", [StringComparison]::OrdinalIgnoreCase) -or
            $c.Trim().StartsWith("$Aqui/", [StringComparison]::OrdinalIgnoreCase)) { $esEste = $true }
      }
    }
    if (-not $esEste) {
      $md5 = [Security.Cryptography.MD5]::Create()
      $hash = -join ($md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($Aqui.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') })
      $nombre = "$base-$($hash.Substring(0, 4))"
    }
  }
  Poner COMPOSE_PROJECT_NAME $nombre
}

# Puerto de la interfaz. En una instalación local el 443 se publica en un puerto al azar para
# que varios leygo convivan; con dominio propio se usan 80 y 443 (los necesita el certificado).
$p = if ($puerto -ne '') { $puerto } else { Leer LEYGO_PUERTO }
if (-not (Es-Puerto $p)) { $p = '80' }
if ($esLocal) {
  Poner LEYGO_HTTPS 443
  $url = if ($p -eq '80') { 'http://localhost' } else { "http://localhost:$p" }
} else {
  Poner LEYGO_HTTPS '443:443'
  if ($p -ne '80') { Write-Host '  ! Con dominio propio conviene el puerto 80: Caddy lo usa para sacar el certificado.' }
  $url = "https://$(Leer DOMAIN)"
}

# ¿El puerto está ocupado por otra cosa (otro leygo, otro servidor)?
function Puerto-Ocupado([int]$n) {
  $c = New-Object System.Net.Sockets.TcpClient
  try {
    $intento = $c.BeginConnect('127.0.0.1', $n, $null, $null)
    if ($intento.AsyncWaitHandle.WaitOne(700)) { $c.EndConnect($intento); return $true }
    return $false
  } catch { return $false } finally { $c.Close() }
}
$caddy = (Docker-Texto compose ps -q caddy).Trim()
if ($caddy -eq '' -and (Puerto-Ocupado ([int]$p))) {
  Write-Host ''
  Write-Host "✗ El puerto $p ya está en uso en este computador (¿otro leygo u otro servidor?)."
  Write-Host '  Elige otro: .\instalar.ps1 -Puerto 8080'
  Salir 1
}
Poner LEYGO_PUERTO $p
Poner LEYGO_URL_LOCAL $url

Write-Host "  • Dominio → $(Leer DOMAIN)$(if ($esLocal) { ' (local)' })"
Write-Host "  • Puerto  → $p"
Write-Host "  • Proyecto de Docker → $(Leer COMPOSE_PROJECT_NAME)"

if ($version -ne '') { Poner LEYGO_VERSION ($version -replace '^v', '') }
$v = Leer LEYGO_VERSION
Write-Host "  • Versión → $(if ($v) { $v } else { 'la última' })"
Write-Host ''

# ─── Levantar ─────────────────────────────────────────────────────────────────
# Se mira solo el código de salida: los errores de docker ya quedaron en la consola.
if (-not $build) { Docker-Consola compose up -d --remove-orphans }
elseif (Test-Path -LiteralPath (Join-Path $Aqui 'Dockerfile')) { Docker-Consola compose up -d --build --remove-orphans }
else {
  Write-Host 'Descargando leygo…'
  Docker-Consola compose pull --quiet
  if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '✗ No se pudieron descargar las imágenes de leygo.'
    Write-Host "  Si el error dice `"unauthorized`" o `"denied`", la versión pedida ($(if ($v) { $v } else { 'latest' })) todavía no está"
    Write-Host '  publicada o no es pública en ghcr.io. Revisa https://leygo.cl o prueba más tarde.'
    Write-Host '  Si dice "toomanyrequests", espera unos minutos y vuelve a correr .\instalar.ps1'
    Salir 1
  }
  Docker-Consola compose up -d --remove-orphans
}
if ($LASTEXITCODE -ne 0) { Write-Host ''; Write-Host '✗ docker compose no pudo levantar leygo (el error está arriba).'; Salir 1 }
# El Caddyfile va montado como archivo: "up -d" no reinicia Caddy si solo cambió él. Reiniciar lo vuelve a montar.
Docker-Texto compose restart caddy | Out-Null

Write-Host ''
Write-Host "Listo. Abre $url"

# Instalación sin configurar: se espera a que leygo arranque y se muestra el código del asistente.
$codigo = ''
$textoEnv = [IO.File]::ReadAllText($ArchivoEnv)
$textoGui = if (Test-Path -LiteralPath $envGui) { [IO.File]::ReadAllText($envGui) } else { '' }
$configurado = "$textoEnv`n$textoGui" -match "(?m)^(ADMIN_API_KEY|GUI_PASSWORD_HASH)=['`"]?[^'`"\s]"
if (-not $configurado) {
  Write-Host -NoNewline 'Esperando que leygo arranque'
  for ($i = 0; $i -lt 45; $i++) {
    $logs = Docker-Texto compose logs agent
    # Tolerante con los acentos por si la consola cambió la codificación.
    $m = [regex]::Matches($logs, 'C.{1,2}digo de configuraci.{1,2}n: *([A-Za-z0-9-]+)')
    if ($m.Count) { $codigo = $m[$m.Count - 1].Groups[1].Value; break }
    Write-Host -NoNewline '.'; Start-Sleep -Seconds 2
  }
  Write-Host ''
}
if ($codigo) {
  Write-Host "Código de configuración: $codigo"
} else {
  Write-Host 'La primera vez te pide un código de un solo uso. Lo ves con:'
  Write-Host "  cd `"$Aqui`"; docker compose logs agent | Select-String -Context 0,4 'configuraci'"
}
Write-Host ''
Write-Host "Los comandos de docker compose se corren dentro de $Aqui"
Write-Host "Para actualizar: cd `"$Aqui`"; .\instalar.ps1"
Write-Host '  (si Windows no deja correr scripts: powershell -ExecutionPolicy Bypass -File .\instalar.ps1)'
Salir 0
