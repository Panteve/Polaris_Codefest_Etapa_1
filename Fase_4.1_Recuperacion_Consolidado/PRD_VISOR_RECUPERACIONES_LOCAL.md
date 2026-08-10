# PRD — Visor local de respuestas de recuperación

**Fase:** 4.1 — Recuperación consolidada  
**Estado:** Propuesta funcional  
**Tipo de solución:** aplicación local con Node.js y frontend HTML, CSS y JavaScript puro

## 1. Contexto

La fase 4.1 contiene varias configuraciones de recuperación, organizadas en carpetas independientes. Cada configuración puede incluir un índice FAISS, su `metadata.jsonl`, un `recuperar.py`, documentación y, eventualmente, un archivo de resultados.

Se requiere una página local que permita seleccionar cada configuración mediante un botón y visualizar sus respuestas de forma ordenada, sin publicar el proyecto en un host.

Este PRD se fundamenta en el contexto disponible del proyecto y en las especificaciones técnicas del reto: cada consulta debe mostrar hasta 3 documentos relevantes y 10 fragmentos, con trazabilidad mediante `query_id`, `doc_id`, `chunk_id` y texto del fragmento.

## 1A. SelecciÃ³n y comparaciÃ³n de configuraciones

La interfaz ofrecerÃ¡ dos formas de consultar los recuperadores:

1. **Vista individual:** el usuario selecciona una configuraciÃ³n y ejecuta una pregunta Ãºnicamente contra ella.
2. **Vista comparativa:** el usuario marca dos o mÃ¡s configuraciones y pulsa `Comparar seleccionadas`. Node.js ejecutarÃ¡ la misma pregunta en cada carpeta y devolverÃ¡ un resultado independiente por configuraciÃ³n.

El panel de configuraciones incluirÃ¡ casillas individuales, `Seleccionar todas`, `Limpiar selecciÃ³n`, `Ver individual` y `Comparar seleccionadas`.

En modo comparativo, las respuestas se mostrarÃ¡n en tarjetas separadas, identificadas por el nombre de la configuraciÃ³n. Cada tarjeta conservarÃ¡ sus propios documentos, fragmentos, scores, tiempo de ejecuciÃ³n y errores. No se mezclarÃ¡n rankings entre recuperadores.

La comparaciÃ³n debe permitir revisar los 3 documentos y los 10 fragmentos de cada configuraciÃ³n. Si una configuraciÃ³n falla, las demÃ¡s deben seguir mostrando sus resultados.

## 1B. Versiones de los scripts de recuperaciÃ³n

Cada carpeta de recuperaciÃ³n podrÃ¡ contener varias versiones del script, por ejemplo:

```text
01_bge_m3_corpus/
├── recuperar_V1.py
├── recuperar_V2.py
└── recuperar_V3.py
```

Node.js debe detectar automÃ¡ticamente los archivos que cumplan el patrÃ³n `recuperar_VN.py` y exponer sus versiones en la lista de configuraciones. La interfaz mostrarÃ¡ un selector de versiÃ³n dentro de cada tarjeta.

El usuario podrÃ¡ elegir una versiÃ³n para la vista individual. En la vista comparativa, cada configuraciÃ³n seleccionada podrÃ¡ usar la versiÃ³n que el usuario elija. Si no se selecciona una versiÃ³n, se usarÃ¡ la mÃ¡s reciente por nÃºmero de versiÃ³n.

Para mantener compatibilidad con las carpetas actuales, un archivo llamado `recuperar.py` sin sufijo se registrarÃ¡ como versiÃ³n `base`.

La versiÃ³n elegida debe aparecer en la tarjeta de resultados y en el historial de la consulta. Node.js debe validar la combinaciÃ³n `configuracion + version` contra los archivos detectados y nunca aceptar rutas de script enviadas directamente por el navegador.

## 2. Objetivo

Construir un visor local para comparar y revisar visualmente las respuestas producidas por las distintas recuperaciones de la fase 4.1.

El usuario debe poder:

1. Abrir una página desde la máquina local.
2. Ver una tarjeta o botón por cada carpeta de recuperación.
3. Elegir una consulta individual.
4. Consultar los 3 documentos y los 10 fragmentos recuperados.
5. Ver score, fuente y metadata cuando estén disponibles.
6. Cambiar de configuración sin recargar manualmente cada carpeta.

## 3. Alcance del MVP

### Incluido

- Servidor local Node.js ejecutado únicamente en `localhost`.
- HTML semántico.
- CSS puro, responsive y sin frameworks.
- JavaScript puro, sin dependencias externas ni CDN.
- Descubrimiento de las carpetas de recuperación desde Node.js.
- Ejecución del `recuperar.py` correspondiente mediante Node.js.
- Comunicación entre la interfaz y Node.js mediante una API local.
- Lectura y devolución de resultados JSON.
- Selector de configuración de recuperación.
- Selector de consulta.
- Vista de documentos recuperados.
- Vista de fragmentos recuperados.
- Estados de carga, archivo no encontrado, JSON inválido y consulta sin resultados.
- Indicador de la configuración activa y del archivo fuente visualizado.
- Ejecución completamente local, sin hosting ni conexión a internet.

### Fuera del MVP

- Recalcular embeddings en el navegador o en Node.js.
- Cargar directamente archivos `index.faiss` desde JavaScript del navegador.
- Persistencia de resultados en una base de datos.
- Autenticación, usuarios o despliegue web.
- Uso de modelos generativos para resumir o reordenar las respuestas.

## 4. Decisión técnica principal

### Formato de comunicación: JSON

La API local de Node.js debe devolver un objeto JSON por consulta. Los archivos `resultados.json` serán una salida opcional para conservar respuestas ya ejecutadas, no la fuente principal de funcionamiento. El formato JSON se recomienda porque:

- permite cargar todas las consultas de una sola vez;
- es compatible con el resultado ya generado en la fase 4.1;
- facilita validar que cada consulta tenga sus documentos y fragmentos;
- evita tener preguntas y respuestas dispersas en muchos archivos;
- permite agregar scores y metadata sin cambiar la interfaz.

El formato JSON Lines (`.jsonl`) puede mantenerse como formato de intercambio o entrega, pero para el navegador se recomienda generar también una copia JSON como arreglo. El visor debe soportar ambos formatos si se implementa un adaptador local.

### Preguntas escritas individualmente

Se permitirá como opción secundaria un archivo `preguntas.json` por configuración. No se recomienda escribir preguntas directamente dentro de `index.html`, porque dificulta mantenerlas y compararlas.

Ejemplo:

```json
[
  {
    "query_id": "q001",
    "text": "¿Qué capacidades de inteligencia artificial se destacan?"
  }
]
```

Si las preguntas ya vienen dentro de cada objeto de `resultados.json`, `preguntas.json` será opcional.

## 5. Arquitectura obligatoria

La aplicación tendrá un único modo de funcionamiento: un servidor Node.js local que sirve la interfaz y coordina la ejecución de los recuperadores Python.

Node.js no reemplazará a Python ni ejecutará FAISS. Su responsabilidad será:

1. Servir `index.html`, `styles.css` y el JavaScript del frontend.
2. Enumerar las carpetas de recuperación autorizadas.
3. Recibir desde la interfaz el identificador de la carpeta y la pregunta.
4. Ejecutar el `recuperar.py` de la carpeta seleccionada.
5. Recibir el resultado JSON del proceso Python.
6. Devolver la respuesta a la interfaz.

Flujo único:

```text
node server.js → abrir localhost → elegir recuperación → escribir pregunta →
Node ejecuta recuperar.py → recibir JSON → visualizar documentos y fragmentos
```

El servidor debe escuchar solo en `127.0.0.1` y no debe publicar ningún puerto hacia internet.

### API local mínima

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/api/configuraciones` | Devuelve las carpetas de recuperación disponibles. |
| `POST` | `/api/recuperar` | Ejecuta el recuperador seleccionado con una pregunta. |
| `GET` | `/api/health` | Confirma que Node.js está activo. |

Ejemplo de petición a `/api/recuperar`:

```json
{
  "configuracion": "01_bge_m3_corpus",
  "pregunta": "¿Qué capacidades de inteligencia artificial se destacan?"
}
```

El endpoint debe validar que la configuración corresponda a una carpeta permitida. No debe aceptar rutas arbitrarias enviadas por el navegador.

## 6. Estructura de carpetas propuesta

```text
Fase_4.1_Recuperacion_Consolidado/
├── server.js                          # servidor Node y API local
├── package.json
├── public/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── 01_bge_m3_corpus/
│   ├── recuperar.py
│   ├── index.faiss
│   ├── metadata.jsonl
│   ├── resultados.json                # salida opcional/cache
│   ├── preguntas.json                 # opcional, catálogo de preguntas
│   └── README.md
├── 03_granite_corpus/
│   ├── recuperar.py
│   ├── index.faiss
│   ├── metadata.jsonl
│   ├── resultados.json                # se genera cuando exista
│   └── README.md
└── ...
```

Node.js será responsable de detectar y validar las carpetas. No se usará un archivo de configuración obligatorio para mantener una lista duplicada; si se necesitan nombres amigables, podrá existir un `configuraciones.json` opcional como metadata del servidor.

Ejemplo:

```json
[
  {
    "id": "01_bge_m3_corpus",
    "nombre": "BGE-M3 — corpus",
    "rutaResultados": "01_bge_m3_corpus/resultados.json",
    "rutaPreguntas": "01_bge_m3_corpus/preguntas.json",
    "descripcion": "Recuperación densa con BGE-M3"
  },
  {
    "id": "03_granite_corpus",
    "nombre": "Granite — corpus",
    "rutaResultados": "03_granite_corpus/resultados.json",
    "descripcion": "Recuperación con Granite"
  }
]
```

## 7. Contrato de datos

El visor debe aceptar el esquema de resultados definido por el reto:

```json
[
  {
    "query_id": "q001",
    "query": "Texto de la pregunta",
    "documents": [
      { "rank": 1, "doc_id": "DOC-042", "score": 0.91 },
      { "rank": 2, "doc_id": "DOC-017", "score": 0.87 },
      { "rank": 3, "doc_id": "DOC-091", "score": 0.82 }
    ],
    "fragments": [
      {
        "rank": 1,
        "chunk_id": "DOC-042-chunk-007",
        "doc_id": "DOC-042",
        "text": "Texto del fragmento...",
        "score": 0.91,
        "fuente": "documento.pdf",
        "idioma": "es",
        "fenomeno": "1"
      }
    ]
  }
]
```

Reglas del adaptador:

- `query_id` es obligatorio.
- `documents` y `fragments` deben ser arreglos.
- El visor mostrará los elementos disponibles aunque falten scores opcionales.
- El texto faltante se mostrará como “Sin texto disponible”.
- Se conservarán los identificadores originales; la interfaz no los debe reemplazar.
- Se podrá mostrar una alerta si no hay exactamente 3 documentos o 10 fragmentos.

## 7A. SelecciÃ³n de versiÃ³n

La respuesta de `GET /api/configuraciones` incluirÃ¡ las versiones encontradas para cada carpeta:

```json
[
  {
    "id": "01_bge_m3_corpus",
    "nombre": "BGE-M3 — corpus",
    "versiones": ["V1", "V2", "V3"]
  }
]
```

La peticiÃ³n de ejecuciÃ³n incluirÃ¡ la versiÃ³n elegida:

```json
{
  "configuracion": "01_bge_m3_corpus",
  "version": "V2",
  "pregunta": "Texto de la pregunta"
}
```

Node.js resolverÃ¡ internamente `01_bge_m3_corpus + V2` hacia `recuperar_V2.py`. La interfaz no enviarÃ¡ rutas de archivos ni comandos completos.

## 8. Requisitos funcionales

### RF-01 — Carga de configuraciones

Al abrir la página, se solicitará a Node.js la lista de carpetas mediante `GET /api/configuraciones` y se mostrará una tarjeta por configuración.

### RF-02 — Selección por botón

Cada tarjeta tendrá un botón “Ver resultados”. Al pulsarlo, la interfaz cargará únicamente los datos de esa configuración y marcará el botón activo.

### RF-03 — Selección de consulta

La interfaz tendrá un `select`, buscador o lista de botones para seleccionar `q001`, `q002`, etc. La pregunta correspondiente se mostrará encima de los resultados.

### RF-04 — Resumen de la respuesta

Se mostrará:

- configuración activa;
- `query_id`;
- texto de la pregunta, si existe;
- cantidad de documentos cargados;
- cantidad de fragmentos cargados;
- advertencias de integridad, si aplican.

### RF-05 — Documentos recuperados

Se mostrarán en orden de ranking, con `rank`, `doc_id` y `score` cuando estén disponibles.

### RF-06 — Fragmentos recuperados

Se mostrarán en orden de ranking, con `rank`, `chunk_id`, `doc_id`, texto y metadata disponible. Cada fragmento deberá poder expandirse o contraerse.

### RF-07 — Navegación entre recuperaciones

Cambiar de configuración debe limpiar la vista anterior, mostrar un estado de carga y luego renderizar los nuevos resultados.

### RF-08 — Errores comprensibles

La interfaz debe informar si falta `resultados.json`, si el archivo no es válido o si una configuración aún no tiene resultados generados.

### RF-09 — Reinicio local

Debe existir un botón “Recargar datos” para volver a leer los archivos sin reiniciar la aplicación.

### RF-00A — Versiones de recuperador

Cada configuraciÃ³n mostrarÃ¡ las versiones de script detectadas en un selector. El usuario podrÃ¡ escoger la versiÃ³n antes de ejecutar una consulta.

### RF-00B — Versiones en comparaciÃ³n

En una comparaciÃ³n, cada configuraciÃ³n conservarÃ¡ su versiÃ³n seleccionada y la interfaz mostrarÃ¡ esa versiÃ³n en el resultado correspondiente.

### RF-00C — VersiÃ³n predeterminada

Si el usuario no cambia el selector, se usarÃ¡ la versiÃ³n mÃ¡s reciente detectada. Las carpetas que solo tengan `recuperar.py` usarÃ¡n la versiÃ³n `base`.

## 9. Requisitos no funcionales

- Ejecutable en un navegador moderno de escritorio.
- Sin internet, CDN, frameworks ni dependencias externas.
- Diseño legible para textos largos y consultas en español, inglés y portugués.
- No modificar los archivos de índices, metadata ni resultados.
- No aplicar resumen, traducción, reranking ni generación de texto.
- Mantener separación entre datos, presentación y lógica.
- La aplicación debe abrirse desde la raíz de `Fase_4.1_Recuperacion_Consolidado`.

## 10. Ejecución local

La aplicación no se abrirá mediante doble clic sobre `index.html`. El flujo oficial será:

1. Instalar Node.js y Python en la máquina.
2. Ejecutar `npm install` si se agregan dependencias; el MVP debe intentar no requerir dependencias externas.
3. Ejecutar `node server.js` desde la raíz de la fase 4.1.
4. Abrir `http://127.0.0.1:3000` en el navegador.
5. Elegir una configuración, escribir una pregunta y pulsar “Recuperar”.

Node.js debe resolver las rutas con base en la raíz conocida del proyecto y ejecutar Python usando una llamada segura, con argumentos separados y sin construir comandos concatenando texto del usuario.

## 11. Experiencia de usuario

La pantalla debe tener tres zonas:

```text
┌──────────────────────────────────────────────────────────┐
│ Visor de recuperaciones · Fase 4.1                       │
│ [Recargar datos] [Cargar archivo local]                  │
├──────────────────┬───────────────────────────────────────┤
│ Configuraciones  │ Pregunta seleccionada                 │
│                  │ q001 · texto de la consulta           │
│ [BGE-M3]         ├───────────────────────────────────────┤
│ [Granite]        │ Documentos recuperados                 │
│ [Overlap]        │ 1. DOC-042   score ...                 │
│                  ├───────────────────────────────────────┤
│                  │ Fragmentos recuperados                 │
│                  │ 1. chunk ...                            │
└──────────────────┴───────────────────────────────────────┘
```

La interfaz debe priorizar lectura: panel lateral para configuraciones, selector de consulta en la parte superior y resultados en tarjetas o paneles apilados.

## 12. Criterios de aceptación

- Al abrir la aplicación se identifican las configuraciones disponibles mediante Node.js.
- Cada configuración tiene un botón independiente.
- Al pulsar una configuración y ejecutar una pregunta, Node.js llama al `recuperar.py` correcto.
- Al seleccionar una consulta, se muestran sus documentos y fragmentos sin alterar el orden.
- Los campos `query_id`, `doc_id`, `chunk_id` y `text` se visualizan correctamente.
- Una configuración sin resultados muestra un mensaje accionable y no rompe la página.
- Un JSON inválido muestra un error legible.
- La página funciona sin conexión a internet.
- Ninguna operación del visor usa modelos generativos ni cambia el ranking producido por el recuperador.
- El uso de `recuperar.py` bajo demanda queda separado como una ampliación que requiere lanzador local.

## 13. Plan de implementación

1. Crear `server.js`, `package.json` y la carpeta `public/`.
2. Implementar el descubrimiento seguro de carpetas de recuperación.
3. Implementar `/api/configuraciones`.
4. Implementar `/api/recuperar` para ejecutar el Python seleccionado.
5. Implementar tarjetas de configuraciones, campo de pregunta y paneles de resultados.
6. Agregar validación de estructura, estados de ejecución y estados de error.
7. Agregar soporte para preguntas predefinidas en `preguntas.json`.
8. Documentar la instalación y el comando único para iniciar Node.js.

## 14. Decisión final para iniciar

La solución se implementará únicamente como una aplicación Node.js local. Node.js servirá la página, detectará las configuraciones y ejecutará el `recuperar.py` correspondiente cuando el usuario pulse el botón.

Las preguntas podrán escribirse en el campo de la interfaz o cargarse desde `preguntas.json`. Los resultados se visualizarán en tiempo real y podrán guardarse como `resultados.json` si se requiere conservar la consulta.
