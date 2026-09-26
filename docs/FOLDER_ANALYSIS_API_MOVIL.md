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
| `files` | archivo, **se repite** | Una o varias fotos, en el orden en que se sacaron. Máximo **10 por envío** y **15 MB por foto**. Formatos: JPEG, PNG o WEBP. |

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

### Errores

Todas las respuestas de error tienen la forma `{"detail": "<mensaje en español para el usuario>"}`.

| Código | Cuándo |
|---|---|
| `401` | Token ausente, vencido o inválido. Renovar el token y reintentar. |
| `403` | El rol del usuario no tiene `folder-analysis.edit`. |
| `422` | Sin fotos, más de 10, una foto vacía o de más de 15 MB, o un archivo que no es una imagen legible. El mensaje indica qué foto falló (por ejemplo, "La foto 2 no es una imagen válida"). **Si falla una, no se guarda ninguna.** |

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
