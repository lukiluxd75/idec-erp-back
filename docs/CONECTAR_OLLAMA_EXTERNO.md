# Conectar el motor Ollama externo al dominio `chatbot`

Guía operativa para dejar accesible, desde el backend del ERP, la máquina externa que
corre Ollama (los modelos LLM/visión/embeddings del asistente de trámites). No es
parte del código del dominio — ver `app/domains/chatbot/` y el plan de integración
para el diseño; esto es solo la puesta en marcha de la infraestructura.

Mientras `CHATBOT_OLLAMA_URL` esté vacío o inalcanzable, el backend responde `503`
en `/api/chatbot/chat`, `/api/chatbot/vision`, `/api/chatbot/ingests` y
`/api/chatbot/embeddings/reindex` — el resto del dominio (catálogo, panel admin,
carga de datos) funciona igual sin esto.

---

## 1. En la máquina externa (la que corre Ollama)

### 1.1 Instalar Ollama

- **macOS**: descargar desde [ollama.com/download](https://ollama.com/download) o `brew install ollama`.
- **Linux**: `curl -fsSL https://ollama.com/install.sh | sh`
- **Windows**: instalador desde [ollama.com/download](https://ollama.com/download).

### 1.2 Descargar los 3 modelos que usa el dominio

Los nombres exactos vienen de `app/core/config/settings.py`
(`CHATBOT_CHAT_MODEL`, `CHATBOT_VISION_MODEL`, `CHATBOT_EMBEDDING_MODEL`) — si en la
máquina externa se van a usar otros nombres/tags, hay que ajustar esas variables en
el `.env` del backend para que coincidan exactamente.

```bash
ollama pull gemma4:e4b
ollama pull qwen3-vl:4b
ollama pull nomic-embed-text
```

Verificar que quedaron:

```bash
ollama list
```

### 1.3 Exponer Ollama en la red (no solo localhost)

Por defecto Ollama escucha únicamente en `127.0.0.1:11434` — inalcanzable desde
otra máquina. Hay que decirle que escuche en todas las interfaces:

**macOS (app de escritorio):**
```bash
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
# reiniciar la app Ollama (salir del ícono de la barra de menú y volver a abrirla)
```

**macOS/Linux (corriendo `ollama serve` a mano):**
```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

**Linux (servicio systemd, instalación con el script oficial):**
```bash
sudo systemctl edit ollama.service
```
Agregar:
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```
Luego:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Windows:** Configuración del sistema → Variables de entorno → nueva variable de
usuario `OLLAMA_HOST` = `0.0.0.0:11434` → reiniciar Ollama.

### 1.4 Firewall: abrir el puerto 11434 solo hacia el servidor del backend

Ollama no tiene autenticación propia — cualquiera que llegue al puerto puede usar
los modelos. No lo expongan a toda la red/internet; restrinjan el acceso a la IP
del servidor donde corre `idec-erp-back`.

Ejemplo con `ufw` (Linux), reemplazando `<IP_DEL_BACKEND>`:
```bash
sudo ufw allow from <IP_DEL_BACKEND> to any port 11434 proto tcp
```

En macOS/Windows, configurar la regla equivalente en el firewall del sistema (o del
router, si están en redes distintas).

### 1.5 Verificar desde otra máquina en la red

Desde el servidor del backend (o cualquier máquina con acceso), reemplazando
`<IP_MAQUINA_OLLAMA>`:

```bash
curl http://<IP_MAQUINA_OLLAMA>:11434/api/tags
```

Debería devolver un JSON con los 3 modelos descargados. Si da timeout o "connection
refused", el problema está en el paso 1.3 (Ollama sigue en `127.0.0.1`) o en el
firewall (paso 1.4) — no en el backend todavía.

---

## 2. En el backend del ERP (`idec-erp-back`)

### 2.1 Configurar `.env`

Editar `idec-erp-back/.env` (no `.env.example`, ese es solo la plantilla):

```bash
CHATBOT_OLLAMA_URL="http://<IP_MAQUINA_OLLAMA>:11434"
```

El resto de las variables `CHATBOT_*` (modelos, timeouts, umbral de similitud) ya
traen defaults correctos — solo tocarlas si la máquina externa usa nombres de
modelo distintos a los del paso 1.2.

### 2.2 Reiniciar el backend

Las variables de entorno se leen al arrancar el proceso — si estaba corriendo con
`CHATBOT_OLLAMA_URL` vacío, hay que reiniciarlo para que tome el cambio.

---

## 3. Verificar end-to-end desde el ERP

La forma más simple sin necesitar un JWT a mano: pedirle al panel admin que
reindexe embeddings (`POST /api/chatbot/embeddings/reindex`, requiere permiso
`chatbot.edit`) — si el motor está bien conectado, responde `200` con
`reindexed_count`; si sigue sin conectar, responde `503` con el mensaje de
`ChatEngineUnavailableException`.

Para probar la conversación real: iniciar sesión en el frontend, entrar a
**Asistente de Trámites → Asistente**, y hacer una pregunta como *"quiero poner la
casa a mi nombre"* — debería identificar el trámite de Cambio de Nombre (o el que
corresponda del catálogo cargado) en vez de responder con el mensaje genérico de
"no identifiqué un trámite específico".

---

## 4. Problemas comunes

| Síntoma | Causa probable |
|---|---|
| `503` siempre, mensaje "todavía no está configurado" | `CHATBOT_OLLAMA_URL` sigue vacío en el `.env` que realmente está leyendo el proceso corriendo, o no se reinició el backend después de editarlo |
| `503`, mensaje "no respondió a tiempo" | El host responde pero muy lento — revisar `CHATBOT_CHAT_TIMEOUT_SECONDS`/`CHATBOT_VISION_TIMEOUT_SECONDS`, o que la máquina externa no esté sobrecargada |
| `503`, mensaje "no se pudo conectar" | Firewall (paso 1.4) o Ollama todavía escuchando solo en `127.0.0.1` (paso 1.3) — probar el `curl` del paso 1.5 primero, aislado del backend |
| El chat responde pero nunca identifica ningún trámite | Falta correr `scripts/seed_chatbot_procedures.py` (carga los trámites) y/o el reindexado de embeddings nunca corrió — ver README del script |
| Ollama devuelve error de modelo no encontrado | El nombre en `CHATBOT_CHAT_MODEL`/`CHATBOT_VISION_MODEL`/`CHATBOT_EMBEDDING_MODEL` no coincide exactamente con lo que muestra `ollama list` en la máquina externa |
