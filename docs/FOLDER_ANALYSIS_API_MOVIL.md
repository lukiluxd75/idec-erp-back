# API para la app móvil: "Analizador y extractor de datos de carpetas"

Contrato para el equipo de la app móvil. Con este endpoint, la app envía al backend del
ERP las fotos que el arquitecto saca de un **Folio**, un **Impuesto** (FUR) o un
**Plano**. Las fotos aparecen en la bandeja del módulo **Herramientas OCR+IA →
Analizador y extractor de datos de carpetas** del IDEC de escritorio. Ahí el
arquitecto las clasifica, arrastrándolas a uno de los tres apartados, y las manda a
analizar.

**La app no clasifica el tipo de documento.** Solo envía las fotos.

> Reemplaza el envío actual a `POST /api/folios`. El Detector de Folios deja de
> mostrarse en el escritorio, así que los folios enviados a ese endpoint viejo ya no
> se ven en el IDEC.

---

## Endpoint

```
POST /api/folder-analysis/captures
Content-Type: multipart/form-data
Authorization: Bearer <access_token de Keycloak>
```

- **Base URL**: la misma del resto de la API del ERP.
- **Autenticación**: el mismo token de Keycloak (realm `alcaldia-idec`) con el que la
  app ya consume el ERP. La foto queda asociada al usuario del token, y solo ese
  usuario la ve en el escritorio.
- **Permiso**: el rol del usuario necesita `folder-analysis.edit`. Se asigna en la
  pantalla de Roles del ERP.

### Cuerpo (multipart)

| Campo | Tipo | Detalle |
|---|---|---|
| `files` | archivo, **se repite** | Una o varias fotos, en el orden en que se sacaron. **No hay tope de cuántas**: lo único que se limita es **15 MB por archivo** y **300 MB por envío** (lo que el servidor sostiene en memoria mientras lo lee entero). Formatos: JPEG, PNG, WEBP o **PDF**. |

Un documento de varias páginas, como un folio o un plano grande, se puede enviar en un
solo envío con varias `files`, o en varios envíos. En el escritorio el arquitecto
arma el documento y ordena las páginas.

### Ejemplo

```bash
curl -X POST "https://<base-del-erp>/api/folder-analysis/captures" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@pagina1.jpg" \
  -F "files=@pagina2.jpg"
```

### Respuesta `201 Created`

Una entrada por foto, en el mismo orden en que se enviaron:

```json
[
  {
    "id": "8f1c0d8e-6f0e-4a0e-9d7a-2b1c3d4e5f60",
    "file_name": "pagina1.jpg",
    "status": "inbox",
    "created_at": "2026-09-24T12:40:03.512Z"
  }
]
```

`status: "inbox"` significa que la foto está en la bandeja del arquitecto, sin
clasificar. La app no necesita guardar el `id` para nada más.

### PDF

Un PDF se separa en el servidor en **una foto por página**, sin tope de páginas --una
carpeta entera escaneada de una vez es un caso normal--, y
desde ahí es indistinguible de una foto del celular: se clasifica, se ordena y se
lee igual, en los tres carriles. Por eso la respuesta puede traer **más entradas
que archivos enviados**: cada página vuelve como su propia captura, en orden de
lectura, con el nombre del PDF y el número de página (`contrato · pág. 2`).

### Errores

Todas las respuestas de error tienen la forma `{"detail": "<mensaje en español para el usuario>"}`.

| Código | Cuándo |
|---|---|
| `401` | Token ausente, vencido o inválido. Renovar el token y reintentar. |
| `403` | El rol del usuario no tiene `folder-analysis.edit`. |
| `422` | Sin archivos, un envío de más de 300 MB en total, uno vacío o de más de 15 MB, un archivo que no es una imagen legible, o un PDF ilegible o con contraseña. El mensaje empieza con el nombre del archivo que falló (por ejemplo, `folio.pdf: El PDF no se pudo abrir…`); el del envío demasiado pesado dice que se manden en dos tandas. **Si falla uno, no se guarda ninguno.** |

---

## Indicador "Celular conectado"

En el escritorio, la bandeja muestra **Celular conectado / Celular no conectado**.
Sirve para que el arquitecto pueda descartar lo primero cuando no le llegan fotos.

### Ya funciona sin cambios en la app

El backend registra el celular en el `POST /login` y en cada `POST /refresh`, que
la app ya llama. Reconoce a la app por el `User-Agent`: vale cualquier cliente que
**no sea un navegador** (`okhttp/…`, `Dart/… (dart:io)`, `ktor`, `CFNetwork/…`),
así que no hay que declarar nada especial. El navegador del PC no cuenta, para que
subir archivos desde el escritorio no encienda el indicador.

Una sesión registrada dura **2 horas** y se renueva con cada refresh de token, así
que con la app abierta el indicador se mantiene encendido.

### Para que sea exacto: dos llamadas

```
POST   /api/presence/session    <- justo después de iniciar sesión
DELETE /api/presence/session    <- al cerrar sesión
```

- Sin cuerpo, las dos. `Authorization: Bearer <access_token>` como el resto.
- Respuesta `200`: `{"mobile_connected": true|false}`.
- `GET /api/presence/session` devuelve el estado actual, útil para verificar que
  la app quedó registrada.

**`DELETE` es la importante.** Es lo único que apaga el indicador *en el momento*:
borra toda la presencia de celular de esa cuenta, incluida la de las fotos subidas
hace un rato. Sin esa llamada el indicador se apaga solo, pero recién cuando vence
la sesión de 2 horas.

Llamar a `POST` cada 15 o 30 minutos mientras la app esté abierta mantiene la
sesión fresca aunque el token no se refresque en ese rato.

### Si la app se cierra sin avisar

Si el usuario la mata desde el administrador de tareas o el celular se queda sin
batería, no llega ningún `DELETE`. El indicador se apaga cuando vence la sesión,
como máximo 2 horas después de la última señal.

---

## Qué pasa después (solo como contexto, no lo hace la app)

1. La foto aparece en la bandeja del escritorio. La web consulta cada pocos segundos.
2. El arquitecto la arrastra al apartado **Folio**, **Impuesto** o **Plano** y
   presiona **Analizar**.
3. El folio y el impuesto se leen en el servidor con OCR y reglas: tardan segundos
   y la pantalla muestra el avance foto por foto. El plano se reparte entre las PCs
   con GPU de los arquitectos, que extraen los datos con el modelo de visión.
4. El arquitecto revisa y corrige los datos, y los guarda como JSON. La lectura
   marca los campos que leyó con poca confianza, para que los compare con la foto.

## Recomendaciones para las fotos

- La hoja completa dentro del cuadro, sin cortar bordes, y con buena luz y sin sombras.
- Enviar la foto original de la cámara, sin comprimirla. El backend la ajusta: la
  endereza, corrige la orientación EXIF y reduce su tamaño.
- En el folio, que se lea el pie "Pag. X de N". Así el sistema reconoce qué página es.
