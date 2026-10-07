-- En qué anda la lectura en servidor de un documento, mientras dura.
--
-- Por qué hace falta una columna y no alcanza con los estados que ya hay: el
-- estado del documento dice "processing" y el de cada foto dice si ya se leyó,
-- pero cuando la última foto queda leída todavía faltan dos pasadas que trabajan
-- sobre el documento entero -- buscar los sellos en las fotos y, al final,
-- mirarlas con el modelo de visión (qwen3-vl) en las computadoras de los
-- arquitectos. Esa última tarda entre veinte y treinta segundos por foto, y sin
-- este cartel la pantalla decía "Interpretando" y se quedaba quieta un minuto,
-- sin forma de saber si estaba trabajando o colgada.
--
-- Valores: 'seals', 'vision' (ReadingStage, en
-- app/domains/folder_analysis/domain/entities/folder_document.py), y NULL
-- mientras se leen las fotos --eso ya lo cuenta el estado de cada una-- y cuando
-- la lectura terminó.
--
-- Ejecutar en PostgreSQL. La aplicación también agrega esta columna al arrancar
-- (app/domains/folder_analysis/infrastructure/models.py); este script existe
-- para aplicarla a mano en un entorno ya desplegado.

ALTER TABLE folder_analysis.documents
    ADD COLUMN IF NOT EXISTS stage VARCHAR(20);

COMMENT ON COLUMN folder_analysis.documents.stage IS
    'En qué pasada de la lectura está ahora mismo (seals, vision); NULL cuando no está en ninguna.';

-- Los documentos que ya existían quedan en NULL, que es lo correcto: ninguno
-- está siendo leído ahora mismo, y una lectura vieja no está en ninguna pasada.
