# drug_database.py
from dataclasses import dataclass
from typing import Optional
import math


@dataclass(frozen=True)
class DrugProfile:
    """Perfil farmacocinético de un ñfármaco."""
    name: str                        # nombre comercial/genérico
    ke: float                        # constante de eliminación [h⁻¹]
    V_mL: float                      # volumen de distribución [mL]
    CMB: float                       # concentración mínima efectiva [µg/mL]
    typical_dose_mg: float           # dosis oral típica por toma [mg]
    max_dose_per_day_mg: float       # dosis máxima diaria [mg]
    absorption_gamma: Optional[float] = None  # γ absorción; None → usa ke
    local_action: bool = False       # True = acción local, no modelar sistémicamente
    notes: str = ""

    @property
    def gamma(self) -> float:
        """Tasa de absorción (usa ke si no se especifica)."""
        return self.absorption_gamma if self.absorption_gamma else self.ke

    @property
    def half_life_h(self) -> float:
        """Vida media [h]"""
        return math.log(2) / self.ke if self.ke > 0 else float('inf')

# Base de datos
DRUG_DB: dict[str, DrugProfile] = {

    # Analgésicos / Antipiréticos
    "amoxicilina": DrugProfile(
        name="Amoxicilina",
        ke=1.12,
        V_mL=42_000,
        CMB=0.3,
        typical_dose_mg=500,
        max_dose_per_day_mg=3_000,
        absorption_gamma=1.12,
        notes="Antibiótico β-lactámico. Perfil validado experimentalmente.",
    ),

    "paracetamol": DrugProfile(
        name="Paracetamol (Acetaminofén)",
        ke=0.38,
        V_mL=50_000,       # ~0.7 L/kg × 70 kg → 49 000 mL
        CMB=4.0,           # concentración mínima analgésica ~4 µg/mL
        typical_dose_mg=500,
        max_dose_per_day_mg=4_000,
        absorption_gamma=1.2,  # absorción rápida, γ > ke
        notes="Analgésico/antipirético. No AINEs. Hepatotóxico en sobredosis.",
    ),

    "ibuprofeno": DrugProfile(
        name="Ibuprofeno",
        ke=0.30,
        V_mL=9_800,        # ~0.14 L/kg × 70 kg
        CMB=10.0,          # ~10 µg/mL para efecto antiinflamatorio
        typical_dose_mg=400,
        max_dose_per_day_mg=2_400,
        absorption_gamma=0.9,
        notes="AINE. Tomar con alimentos. Evitar en gastropatía.",
    ),

    "naproxeno": DrugProfile(
        name="Naproxeno",
        ke=0.048,
        V_mL=9_100,        # ~0.13 L/kg
        CMB=25.0,          # µg/mL efecto analgésico
        typical_dose_mg=500,
        max_dose_per_day_mg=1_250,
        absorption_gamma=0.4,
        notes="AINE de vida media larga (~14 h). Dosificación c/12h habitual.",
    ),

    "aspirina": DrugProfile(
        name="Aspirina (Ácido Acetilsalicílico)",
        ke=0.277,          # media geométrica de 0.231 y 0.346
        V_mL=11_200,       # ~0.16 L/kg
        CMB=15.0,          # µg/mL efecto antiinflamatorio
        typical_dose_mg=500,
        max_dose_per_day_mg=4_000,
        absorption_gamma=1.0,
        notes="Ke varía con la dosis (cinética no lineal a dosis altas). "
              "Modelo LTI válido solo a dosis bajas–moderadas.",
    ),

    # Antihistamínicos
    "loratadina": DrugProfile(
        name="Loratadina",
        ke=0.082,
        V_mL=120_000,      # alta lipofilia, Vd ~119 L
        CMB=1.0,           # ng/mL ≡ 0.001 µg/mL; usar 0.001
        typical_dose_mg=10,
        max_dose_per_day_mg=10,
        absorption_gamma=0.5,
        notes="Antihistamínico no sedante. CMB expresada en µg/mL (0.001).",
    ),

    "cetirizina": DrugProfile(
        name="Cetirizina",
        ke=0.099,
        V_mL=56_000,       # Vd ~0.56 L/kg × 70 kg ... conservador
        CMB=0.04,          # ~40 ng/mL en µg/mL
        typical_dose_mg=10,
        max_dose_per_day_mg=10,
        absorption_gamma=0.6,
        notes="Antihistamínico. Excreción renal; ajuste en IR.",
    ),

    # Antitusivos / Expectorantes 
    "dextrometorfano": DrugProfile(
        name="Dextrometorfano",
        ke=0.105,
        V_mL=350_000,      # Vd muy alto ~5 L/kg
        CMB=0.05,          # µg/mL (estimado antitusivo)
        typical_dose_mg=30,
        max_dose_per_day_mg=120,
        absorption_gamma=0.5,
        notes="Antitusivo central. No usar con IMAOs.",
    ),

    "guaifenesina": DrugProfile(
        name="Guaifenesina",
        ke=0.693,
        V_mL=9_800,
        CMB=100.0,         # µg/mL (vida media ~1 h, acción rápida)
        typical_dose_mg=400,
        max_dose_per_day_mg=2_400,
        absorption_gamma=1.5,
        notes="Expectorante. t½ ≈ 1 h. Dosificación frecuente necesaria.",
    ),

    # Descongestionantes 
    "oximetazolina": DrugProfile(
        name="Oximetazolina",
        ke=0.133,
        V_mL=84_000,       # estimado; administración intranasal → absorción sistémica baja
        CMB=0.01,          # µg/mL referencia sistémica
        typical_dose_mg=0.05,   # dosis intranasal ~0.05 mg por aplicación
        max_dose_per_day_mg=0.3,
        absorption_gamma=0.2,
        notes="Descongestionante nasal tópico. Uso sistémico limitado; "
              "el modelo PK es aproximado. No usar >3 días (efecto rebote).",
    ),

    # Antiácidos / GI 
    "carbonato_calcio": DrugProfile(
        name="Carbonato de Calcio",
        ke=0.001,          # placeholder; acción local
        V_mL=1,
        CMB=0.0,
        typical_dose_mg=500,
        max_dose_per_day_mg=2_500,
        local_action=True,
        notes="Antiácido de acción local en el lumen GI. "
              "No tiene perfil PK sistémico modelable con LTI. "
              "Tomar 1–3 veces al día según síntomas.",
    ),

    "subsalicilato_bismuto": DrugProfile(
        name="Subsalicilato de Bismuto",
        ke=0.219,          # media geométrica de 0.138 y 0.346 (fracción salicilato)
        V_mL=11_000,
        CMB=50.0,          # µg/mL salicilato plasmático (referencia)
        typical_dose_mg=524,
        max_dose_per_day_mg=4_192,
        absorption_gamma=0.6,
        notes="Fracción salicilato modelada sistémicamente. "
              "El bismuto per se precipita en el GI.",
    ),

    "loperamida": DrugProfile(
        name="Loperamida",
        ke=0.038,
        V_mL=350_000,      # Vd muy alto ~5 L/kg
        CMB=0.002,         # µg/mL (2 ng/mL referencia antidiarreica)
        typical_dose_mg=4,
        max_dose_per_day_mg=16,
        absorption_gamma=0.2,
        notes="Antidiarreico. t½ ≈ 18 h. Alta unión a proteínas.",
    ),

    "omeprazol": DrugProfile(
        name="Omeprazol",
        ke=1.04,           # media geométrica de 0.693 y 1.38
        V_mL=21_000,       # Vd ~0.3 L/kg
        CMB=0.1,           # µg/mL referencia (inhibición bomba protones)
        typical_dose_mg=20,
        max_dose_per_day_mg=40,
        absorption_gamma=0.8,
        notes="Inhibidor de bomba de protones. Tomar 30 min antes de comer. "
              "Efecto farmacológico persiste más que la concentración plasmática.",
    ),

    "simeticona": DrugProfile(
        name="Simeticona",
        ke=0.001,          # placeholder; acción local
        V_mL=1,
        CMB=0.0,
        typical_dose_mg=80,
        max_dose_per_day_mg=500,
        local_action=True,
        notes="Antiflatulento de acción local. No se absorbe sistémicamente. "
              "Tomar después de comidas y al acostarse según síntomas.",
    ),
}

# Funciones de acceso
def get_drug(name: str) -> Optional[DrugProfile]:
    """
    Busca un fármaco en la BD (insensible a mayúsculas y tildes simples).
    Retorna None si no se encuentra.
    """
    key = name.lower().strip().replace(" ", "_").replace("-", "_")
    # Búsqueda exacta
    if key in DRUG_DB:
        return DRUG_DB[key]
    # Búsqueda parcial
    matches = [v for k, v in DRUG_DB.items() if key in k or k in key]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Retornar el que tenga el nombre más corto (más específico)
        return min(matches, key=lambda d: len(d.name))
    return None


def list_drugs() -> list[str]:
    """Retorna los nombres de todos los fármacos en la BD."""
    return [v.name for v in DRUG_DB.values()]


def get_all_modelable() -> dict[str, DrugProfile]:
    """Retorna solo los fármacos que pueden ser modelados sistémicamente."""
    return {k: v for k, v in DRUG_DB.items() if not v.local_action}