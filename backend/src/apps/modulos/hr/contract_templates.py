"""Plantillas de contratos laborales por caso específico.

Precedente: la plantilla genera el BORRADOR (texto editable por RRHH antes de
emitir). No pretende sustituir asesoría legal: es la base redactada con los
datos reales del trabajador y la empresa, ajustable a cada caso.

Los placeholders se llenan desde Employee + CompanyProfile + datos del contrato.
Campos sin dato quedan como línea para completar a mano ("________").
"""

from __future__ import annotations

from .models import EmploymentContract

BLANK = "________"

_HEADER = (
    "CONTRATO INDIVIDUAL DE TRABAJO — {contract_type_label}\n"
    "\n"
    "Nosotros: {company_legal_name} (RUC {company_tax_id}), con domicilio en "
    "{company_address}, representada en este acto por {employer_rep}, en adelante "
    "\"EL EMPLEADOR\"; y {employee_name}, identificado(a) con cédula "
    "{employee_national_id}, en adelante \"EL TRABAJADOR\", convenimos celebrar el "
    "presente contrato individual de trabajo, conforme al Código del Trabajo vigente, "
    "bajo las cláusulas siguientes:\n"
)

_SALARY_CLAUSE = (
    "TERCERA — SALARIO: EL EMPLEADOR pagará a EL TRABAJADOR un salario de "
    "{salary_text}, pagadero {salary_period_label}, del cual se harán las deducciones "
    "de ley (INSS laboral e IR cuando corresponda).\n"
)

_COMMON_TAIL = (
    "CUARTA — JORNADA: la jornada ordinaria será la establecida por la ley y los "
    "horarios definidos por EL EMPLEADOR según las necesidades de la operación, sin "
    "exceder los máximos legales.\n"
    "QUINTA — OBLIGACIONES: EL TRABAJADOR se obliga a cumplir sus labores con "
    "esmero y eficiencia, acatar las normas internas, y cuidar los bienes y equipos "
    "que se le confíen.\n"
    "SEXTA — PRESTACIONES: EL TRABAJADOR gozará de las prestaciones de ley "
    "(vacaciones, décimo tercer mes, descansos y feriados).\n"
    "SÉPTIMA — Lo no previsto en este contrato se regirá por el Código del Trabajo "
    "y demás leyes aplicables.\n"
    "\n"
    "Leído el presente contrato y conformes con su contenido, firmamos en "
    "{company_city}, a los {signing_date}.\n"
    "\n"
    "\n"
    "______________________________          ______________________________\n"
    "        EL EMPLEADOR                            EL TRABAJADOR\n"
    "   {company_legal_name}                      {employee_name}\n"
)

_TEMPLATES: dict[str, str] = {
    EmploymentContract.ContractType.INDEFINIDO: (
        _HEADER
        + "\n"
        + "PRIMERA — OBJETO: EL TRABAJADOR se obliga a prestar sus servicios como "
        "{position_name}, realizando las labores propias del cargo y las conexas que "
        "se le orienten.\n"
        "SEGUNDA — DURACIÓN: el presente contrato es por TIEMPO INDEFINIDO, "
        "iniciando el {start_date}. Los primeros treinta (30) días se consideran "
        "período de prueba, durante el cual cualquiera de las partes podrá darlo por "
        "terminado sin responsabilidad.\n"
        + _SALARY_CLAUSE
        + _COMMON_TAIL
    ),
    EmploymentContract.ContractType.PLAZO_FIJO: (
        _HEADER
        + "\n"
        + "PRIMERA — OBJETO: EL TRABAJADOR se obliga a prestar sus servicios como "
        "{position_name}, realizando las labores propias del cargo y las conexas que "
        "se le orienten.\n"
        "SEGUNDA — DURACIÓN: el presente contrato es por TIEMPO DETERMINADO, "
        "iniciando el {start_date} y finalizando el {end_date}, fecha en la que "
        "terminará la relación laboral sin necesidad de aviso previo, salvo prórroga "
        "expresa de las partes.\n"
        + _SALARY_CLAUSE
        + _COMMON_TAIL
    ),
    EmploymentContract.ContractType.OBRA: (
        _HEADER
        + "\n"
        + "PRIMERA — OBJETO: EL TRABAJADOR se obliga a ejecutar la obra o servicio "
        "determinado siguiente: {work_description}, en calidad de {position_name}.\n"
        "SEGUNDA — DURACIÓN: el presente contrato inicia el {start_date} y concluirá "
        "al finalizar y entregar la obra o servicio contratado, sin responsabilidad "
        "adicional para las partes.\n"
        + _SALARY_CLAUSE
        + _COMMON_TAIL
    ),
    EmploymentContract.ContractType.TEMPORADA: (
        _HEADER
        + "\n"
        + "PRIMERA — OBJETO: EL TRABAJADOR se obliga a prestar sus servicios como "
        "{position_name} durante la TEMPORADA de {season_description}, realizando "
        "las labores propias de la época (corte, recolección, acopio y conexas).\n"
        "SEGUNDA — DURACIÓN: el presente contrato es POR TEMPORADA, iniciando el "
        "{start_date} y finalizando el {end_date} o al concluir la temporada, lo que "
        "ocurra primero. La terminación por fin de temporada no genera "
        "responsabilidad adicional, sin perjuicio de las prestaciones proporcionales "
        "de ley.\n"
        + _SALARY_CLAUSE
        + _COMMON_TAIL
    ),
}


def render_contract_body(*, contract_type: str, context: dict) -> str:
    """Rellena la plantilla del tipo dado; claves faltantes quedan como BLANK."""
    template = _TEMPLATES[contract_type]

    class _Safe(dict):
        def __missing__(self, key: str) -> str:  # noqa: D105
            return BLANK

    safe = _Safe({k: (v if v not in (None, "") else BLANK) for k, v in context.items()})
    return template.format_map(safe)
