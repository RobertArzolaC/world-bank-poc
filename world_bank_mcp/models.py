"""Pydantic contracts for tool inputs and outputs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from world_bank_mcp.rules import validate_year_range


class SeriesQuery(BaseModel):
    """Validated input for a single-entity indicator series."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str = Field(min_length=1, description="País o agregado del catálogo de la demo.")
    indicator: str = Field(min_length=1, description="Código o nombre de un indicador permitido.")
    start_year: int = Field(description="Año inicial entre 1960 y el año actual.")
    end_year: int | None = Field(
        default=None,
        description="Año final opcional; si se omite, se consulta solo start_year.",
    )

    @model_validator(mode="after")
    def _validate_years(self) -> "SeriesQuery":
        validate_year_range(self.start_year, self.resolved_end_year)
        return self

    @property
    def resolved_end_year(self) -> int:
        return self.end_year if self.end_year is not None else self.start_year


class ComparisonQuery(BaseModel):
    """Validated input for an equivalent two-country comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    country_a: str = Field(min_length=1, description="Primer país del catálogo de la demo.")
    country_b: str = Field(min_length=1, description="Segundo país del catálogo de la demo.")
    indicator: str = Field(min_length=1, description="Indicador compartido por ambos valores.")
    year: int = Field(description="Año único entre 1960 y el año actual.")

    @model_validator(mode="after")
    def _validate_year(self) -> "ComparisonQuery":
        validate_year_range(self.year, self.year)
        return self


class EntityRef(BaseModel):
    iso3: str = Field(description="Código ISO3 de la entidad.")
    name: str = Field(description="Nombre canónico de la entidad.")


class IndicatorRef(BaseModel):
    code: str = Field(description="Código del indicador del Banco Mundial.")
    name: str = Field(description="Nombre canónico del indicador.")


class SeriesPoint(BaseModel):
    year: int = Field(description="Año del dato.")
    value: float | None = Field(description="Valor observado; null cuando el dato falta.")


class SeriesResult(BaseModel):
    indicator: IndicatorRef
    entity: EntityRef
    unit: str = Field(description="Unidad del indicador.")
    source: str = Field(description="Fuente y edición de los datos.")
    retrieved_at: datetime = Field(description="Fecha y hora UTC de la consulta.")
    series: list[SeriesPoint] = Field(description="Serie ascendente por año, con huecos en null.")
    missing_years: list[int] = Field(description="Años solicitados sin dato disponible.")
    warnings: list[str] = Field(description="Advertencias de cobertura e interpretación.")


class CountryValue(BaseModel):
    entity: EntityRef
    value: float = Field(description="Valor observado para el país y año comparados.")


class ComparisonResult(BaseModel):
    indicator: IndicatorRef
    year: int
    unit: str = Field(description="Unidad compartida por ambos valores.")
    source: str = Field(description="Fuente y edición de los datos.")
    retrieved_at: datetime = Field(description="Fecha y hora UTC de la consulta.")
    country_a: CountryValue
    country_b: CountryValue
    difference: float = Field(description="country_a.value - country_b.value, en la misma unidad.")
    warnings: list[str] = Field(description="Advertencias de cobertura e interpretación.")
