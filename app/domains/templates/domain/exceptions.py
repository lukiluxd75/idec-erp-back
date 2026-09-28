from app.core.errors.exceptions import DomainException


class TemplateNotFoundException(DomainException):
    """No existe una plantilla con el id solicitado."""
    http_status = 404


class DuplicateTemplateCodeException(DomainException):
    """Ya existe una plantilla con ese código (columna `codigo`, UNIQUE)."""
    http_status = 409


class VariableNotFoundException(DomainException):
    """No existe una variable con el id solicitado."""
    http_status = 404


class DuplicateVariableKeyException(DomainException):
    """Ya existe una variable con esa clave (columna `clave`, UNIQUE)."""
    http_status = 409


class CiteConfigurationNotFoundException(DomainException):
    """No hay una configuración de CITE (sigla) registrada para esa combinación
    de área + tipo de documento -- hay que crearla antes de poder generar CITEs
    con ella."""
    http_status = 404


class DuplicateCiteConfigurationException(DomainException):
    """Ya existe una configuración de CITE para esa combinación de área + tipo
    de documento (UNIQUE (area_codigo, tipo_documento_codigo))."""
    http_status = 409


class InvalidCiteFormatException(DomainException):
    """El campo `formato` de la sigla usa un placeholder que no es {area}, {tipo},
    {numero} o {gestion} (o tiene una llave sin cerrar)."""
    http_status = 400


__all__ = [
    "TemplateNotFoundException",
    "DuplicateTemplateCodeException",
    "VariableNotFoundException",
    "DuplicateVariableKeyException",
    "CiteConfigurationNotFoundException",
    "DuplicateCiteConfigurationException",
    "InvalidCiteFormatException",
]

class TemplateEngineUnavailableException(DomainException):
    """No se pudo conectar con el Motor de Plantillas Externo, o no está configurado."""
    http_status = 503

class TemplateEngineErrorException(DomainException):
    """El Motor de Plantillas Externo respondió con un error de negocio."""
    http_status = 502
