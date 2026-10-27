"""Validated specifications. Public field names carry their physical units."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any
from urllib.parse import urlsplit


class MeasurementError(ValueError):
    """A measurement cannot support the requested conclusion."""


def finite(value: Any, name: str, minimum: float | None = None,
           maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise MeasurementError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MeasurementError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise MeasurementError(f"{name} must be finite.")
    if minimum is not None and number < minimum:
        raise MeasurementError(f"{name} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise MeasurementError(f"{name} must be at most {maximum}.")
    return number


@dataclass(frozen=True)
class Calibration:
    meters_per_pixel: float | None = None
    pixel_noise_sd: float | None = None
    scale_relative_sd: float = 0.0
    force_relative_sd: float = 0.0
    sample_clock_relative_sd: float | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Calibration:
        if not isinstance(data, dict):
            raise MeasurementError("calibration must be an object.")
        allowed = {f.name for f in fields(cls)}
        if set(data) - allowed:
            raise MeasurementError(f"Unknown calibration fields: {sorted(set(data) - allowed)}")
        out = {}
        for name, value in data.items():
            if value is None and name in {"meters_per_pixel", "pixel_noise_sd", "sample_clock_relative_sd"}:
                out[name] = None
            else:
                out[name] = finite(value, name, 0, .5 if "relative" in name else None)
        for name in ("meters_per_pixel", "pixel_noise_sd"):
            if out.get(name) == 0:
                raise MeasurementError(f"{name} must be positive.")
        return cls(**out)


@dataclass(frozen=True)
class MeasurementSpec:
    domain: str
    question: str
    equipment: list[str] = field(default_factory=lambda: ["recorded data"])
    target_relative_uncertainty: float = .05
    budget_seconds: float = 120
    max_force_n: float = 2
    calibration: Calibration = field(default_factory=Calibration)
    min_frequency_hz: float = 50
    max_frequency_hz: float = 2000
    source_kind: str = "imported"
    source_name: str = "User supplied observations"
    source_limitations: list[str] = field(default_factory=list)
    calibration_basis: str = "User-declared values; independent certificates not verified by this engine"
    source_attribution: list[dict[str, Any]] = field(default_factory=list)
    reference: dict[str, Any] | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | MeasurementSpec) -> MeasurementSpec:
        if isinstance(data, cls):
            data = asdict(data)
        if not isinstance(data, dict):
            raise MeasurementError("Measurement specification must be an object.")
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise MeasurementError(f"Unknown specification fields: {sorted(unknown)}")
        values = dict(data)
        question = values.get("question", "")
        if not isinstance(question, str) or not 3 <= len(question.strip()) <= 2000:
            raise MeasurementError("Describe the scientific question in 3–2000 characters.")
        domain = values.get("domain")
        if domain not in {"stiffness", "acoustic"}:
            raise MeasurementError("Supported domains are stiffness and acoustic resonance.")
        words = question.lower()
        vocabulary = {"stiffness": ("stiff", "spring", "deflect", "compliance", "force", "load"),
                      "acoustic": ("acoustic", "resonan", "frequen", "sound", "tone", "fork", "pitch")}
        if not any(word in words for word in vocabulary[domain]):
            raise MeasurementError(f"The question is outside the supported {domain} compiler. "
                                   "Use a force–deflection or dominant-resonance question.")
        equipment = values.get("equipment", ["recorded data"])
        if not isinstance(equipment, list) or not equipment or len(equipment) > 20 or any(
                not isinstance(x, str) or not x.strip() or len(x) > 200 for x in equipment):
            raise MeasurementError("List at least one available instrument or recorded-data source.")
        values["equipment"] = equipment
        for name, default, lo, hi in (
            ("target_relative_uncertainty", .05, .000001, 1),
            ("budget_seconds", 120, 1, 3600), ("max_force_n", 2, .000001, 10),
            ("min_frequency_hz", 50, 1, 96000), ("max_frequency_hz", 2000, 2, 192000)):
            values[name] = finite(values.get(name, default), name, lo, hi)
        if values["min_frequency_hz"] >= values["max_frequency_hz"]:
            raise MeasurementError("The frequency band must have a positive width.")
        if values.get("source_kind", "imported") not in {"synthetic", "recorded", "imported", "live"}:
            raise MeasurementError("source_kind must be synthetic, recorded, imported or live.")
        source = values.get("source_name", "User supplied observations")
        if not isinstance(source, str) or not source.strip() or len(source) > 500:
            raise MeasurementError("Give the observations a source name (at most 500 characters).")
        values["source_name"] = source
        limitations = values.get("source_limitations", [])
        if (not isinstance(limitations, list) or len(limitations) > 20
                or any(not isinstance(x, str) or len(x) > 2000 for x in limitations)):
            raise MeasurementError("source_limitations must be at most 20 text entries of 2000 characters.")
        basis = values.get("calibration_basis", cls.__dataclass_fields__["calibration_basis"].default)
        if not isinstance(basis, str) or not basis.strip() or len(basis) > 2000:
            raise MeasurementError("Describe the calibration basis in 1–2000 characters.")
        attribution = values.get("source_attribution", [])
        if not isinstance(attribution, list) or len(attribution) > 10:
            raise MeasurementError("source_attribution must be a list of at most 10 source records.")
        required = {"title", "creators", "source_url", "license", "license_url", "modifications"}
        for entry in attribution:
            if not isinstance(entry, dict) or set(entry) != required:
                raise MeasurementError("Source records require title, creators, source_url, license, license_url and modifications.")
            creators = entry["creators"]
            if (not isinstance(creators, list) or not creators or len(creators) > 50
                    or any(not isinstance(x, str) or not 1 <= len(x) <= 200 for x in creators)):
                raise MeasurementError("Source creators must be a nonempty list of names.")
            for key in required - {"creators"}:
                if not isinstance(entry[key], str) or not 1 <= len(entry[key]) <= 2000:
                    raise MeasurementError("Source attribution text must contain 1–2000 characters.")
            for key in ("source_url", "license_url"):
                url = urlsplit(entry[key])
                if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                    raise MeasurementError("Source attribution requires public HTTP(S) URLs without credentials.")
        reference = values.get("reference")
        if reference is not None:
            if not isinstance(reference, dict) or set(reference) != {"value", "unit", "kind"}:
                raise MeasurementError("reference requires value, unit and kind; its independence is not assumed.")
            if reference["unit"] != {"stiffness": "N/m", "acoustic": "Hz"}[domain]:
                raise MeasurementError("Reference units must match the physical quantity.")
            if not isinstance(reference["kind"], str) or not 1 <= len(reference["kind"]) <= 1000:
                raise MeasurementError("Describe the reference kind and evidence limits.")
            values["reference"] = dict(reference, value=finite(reference["value"], "reference value", 1e-30))
        values["calibration"] = Calibration.parse(values.get("calibration", {}))
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
