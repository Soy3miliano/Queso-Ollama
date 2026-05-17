"""
pharma_model.py
Modelo:
    V · dC/dt = f(t) - k·V·C(t)
    H(s) = 1 / (V·(s + k))
    h(t) = (1/V)·e^(-k·t)          ← respuesta al impulso

Parámetros:
    k  : constante de eliminación [h⁻¹]
    V  : volumen de distribución   [mL]
    A0 : dosis                     [µg]
    CMB: concentración mínima bactericida / efectiva [µg/mL]
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# Estructura de resultado
@dataclass
class SimResult:
    """Resultado completo de una simulación."""
    t: np.ndarray                       # vector de tiempo [h]
    C: np.ndarray                       # concentración plasmática [µg/mL]
    C_max: float                        # concentración pico [µg/mL]
    t_max: float                        # tiempo al pico [h]
    t_below_cmb: Optional[float]        # primera vez que C < CMB [h]; None si nunca cae
    drug_name: str
    dose_mg: float
    k: float
    V_mL: float
    CMB: float


@dataclass
class MultiDoseResult:
    """Resultado de simulación multidosis."""
    t: np.ndarray
    C: np.ndarray
    interval_h: float
    optimal_interval_h: float           # intervalo recomendado
    drug_name: str
    CMB: float
    always_above_cmb: bool              # ¿la concentración nunca cae bajo CMB?


# Funciones principales
def impulse_response(t: np.ndarray, k: float, V_mL: float) -> np.ndarray:
    """
    Respuesta al impulso del sistema LTI monocompartimental.
        h(t) = (1/V) · e^(-k·t)

    Args:
        t     : vector tiempo [h]
        k     : constante de eliminación [h⁻¹]
        V_mL  : volumen de distribución [mL]

    Returns:
        h(t) en [mL⁻¹] (se multiplica por µg para dar µg/mL)
    """
    return (1.0 / V_mL) * np.exp(-k * t)


def theoretical_input(t: np.ndarray, A0_ug: float, gamma: float) -> np.ndarray:
    """
    Función de entrada teórica (absorción gastrointestinal).
        f(t) = A0 · γ · e^(-γ·t)    [µg/h]

    Args:
        t      : vector tiempo [h]
        A0_ug  : dosis inicial [µg]
        gamma  : tasa de absorción ≈ k [h⁻¹]

    Returns:
        f(t) [µg/h]
    """
    return A0_ug * gamma * np.exp(-gamma * t)


def simulate_single_dose(
    k: float,
    V_mL: float,
    A0_mg: float,
    CMB: float,
    drug_name: str = "Fármaco",
    dt: float = 0.01,
    t_end: float = 24.0,
    gamma: Optional[float] = None,
) -> SimResult:
    """
    Simula la concentración plasmática tras una dosis única.
    Usa convolución: C(t) = f(t) * h(t)  (operador convolución)

    Args:
        k        : constante de eliminación [h⁻¹]
        V_mL     : volumen de distribución [mL]
        A0_mg    : dosis [mg]  → se convierte internamente a µg
        CMB      : concentración mínima bactericida/efectiva [µg/mL]
        drug_name: nombre del fármaco
        dt       : paso temporal [h]  (resolución de la simulación)
        t_end    : duración de la simulación [h]
        gamma    : tasa de absorción. Si None, se usa k (mismo valor).

    Returns:
        SimResult con todos los parámetros de la respuesta.
    """
    if gamma is None:
        gamma = k

    A0_ug = A0_mg * 1_000.0          # mg → µg

    t = np.arange(0, t_end + dt, dt)

    f_t  = theoretical_input(t, A0_ug, gamma)   # entrada [µg/h]
    h_t  = impulse_response(t, k, V_mL)         # respuesta al impulso [mL⁻¹]

    # Convolución discreta (≡ integral de Duhamel)
    C_full = np.convolve(f_t, h_t) * dt
    C = C_full[:len(t)]                          # truncar al largo original

    C_max  = float(np.max(C))
    t_max  = float(t[np.argmax(C)])

    # Primera caída por debajo de CMB (después del pico)
    idx_peak = int(np.argmax(C))
    below = np.where(C[idx_peak:] < CMB)[0]
    t_below_cmb = float(t[idx_peak + below[0]]) if len(below) > 0 else None

    return SimResult(
        t=t, C=C, C_max=C_max, t_max=t_max,
        t_below_cmb=t_below_cmb,
        drug_name=drug_name, dose_mg=A0_mg,
        k=k, V_mL=V_mL, CMB=CMB,
    )


def simulate_multi_dose(
    k: float,
    V_mL: float,
    A0_mg: float,
    CMB: float,
    interval_h: float,
    drug_name: str = "Fármaco",
    dt: float = 0.01,
    t_final: float = 48.0,
    gamma: Optional[float] = None,
) -> MultiDoseResult:
    """
    Simula régimen multidosis usando el principio de superposición (LTI).
    Cada dosis es una copia desplazada en el tiempo de la respuesta a dosis única.

    Args:
        interval_h : intervalo entre dosis [h]
        t_final    : duración total de la simulación [h]
        (resto de args igual que simulate_single_dose)

    Returns:
        MultiDoseResult
    """
    if gamma is None:
        gamma = k

    A0_ug = A0_mg * 1_000.0
    t_sim = np.arange(0, t_final + dt, dt)

    # Respuesta a dosis única (en ventana larga para poder desplazar)
    t_single = np.arange(0, t_final + dt, dt)
    f_single = theoretical_input(t_single, A0_ug, gamma)
    h_single = impulse_response(t_single, k, V_mL)
    C_single_full = np.convolve(f_single, h_single) * dt
    C_single = C_single_full[:len(t_single)]

    # Superposición: suma de dosis desplazadas
    num_doses = int(np.floor(t_final / interval_h))
    C_total = np.zeros(len(t_sim))

    for j in range(num_doses):
        t_delay = j * interval_h
        t_shifted = t_sim - t_delay
        # Interpolación de la respuesta desplazada
        C_shifted = np.interp(t_shifted, t_single, C_single, left=0.0, right=0.0)
        C_total += C_shifted

    # ¿Se mantiene siempre sobre CMB (después de la primera hora)?
    idx_1h = int(1.0 / dt)
    always_above = bool(np.all(C_total[idx_1h:] >= CMB))

    return MultiDoseResult(
        t=t_sim, C=C_total,
        interval_h=interval_h,
        optimal_interval_h=interval_h,   # se calcula externamente
        drug_name=drug_name,
        CMB=CMB,
        always_above_cmb=always_above,
    )


def find_optimal_interval(
    k: float,
    V_mL: float,
    A0_mg: float,
    CMB: float,
    drug_name: str = "Fármaco",
    candidates: list = None,
    dt: float = 0.01,
    t_final: float = 72.0,
    gamma: Optional[float] = None,
) -> dict:
    """
    Determina el intervalo de dosificación óptimo entre una lista de candidatos.

    Criterio (en orden de prioridad):
      1. La concentración se mantiene ≥ CMB en todo momento (tras la primera hora).
      2. El pico máximo en estado estacionario es lo más bajo posible
         (minimizar riesgo de toxicidad).
      3. El intervalo más largo que cumpla lo anterior (comodidad para el paciente).

    Args:
        candidates : lista de intervalos a evaluar [h].
                     Default: [2, 4, 6, 8, 12, 24]

    Returns:
        dict con:
            'optimal_interval_h'  : intervalo recomendado [h]
            'results'             : {intervalo: MultiDoseResult}
            'summary'             : tabla resumen
    """
    if candidates is None:
        candidates = [2, 4, 6, 8, 12, 24]

    results = {}
    summary = []

    for iv in candidates:
        r = simulate_multi_dose(
            k=k, V_mL=V_mL, A0_mg=A0_mg, CMB=CMB,
            interval_h=iv, drug_name=drug_name,
            dt=dt, t_final=t_final, gamma=gamma,
        )
        # Métricas en estado estacionario (segunda mitad de la simulación)
        mid = len(r.t) // 2
        C_ss = r.C[mid:]
        peak_ss  = float(np.max(C_ss))
        trough_ss = float(np.min(C_ss))

        results[iv] = r
        summary.append({
            'interval_h'    : iv,
            'always_above'  : r.always_above_cmb,
            'peak_ss'       : peak_ss,
            'trough_ss'     : trough_ss,
        })

    # Selección: mayor intervalo que mantiene trough ≥ CMB
    valid = [s for s in summary if s['trough_ss'] >= CMB]

    if valid:
        # El más largo entre los válidos
        optimal = max(valid, key=lambda s: s['interval_h'])
    else:
        # Si ninguno cumple, elegir el que más se acerca al CMB por arriba
        optimal = min(summary, key=lambda s: abs(s['trough_ss'] - CMB))

    opt_interval = optimal['interval_h']

    # Marcar el resultado óptimo
    for iv, r in results.items():
        r.optimal_interval_h = opt_interval

    return {
        'optimal_interval_h': opt_interval,
        'results': results,
        'summary': summary,
        'is_valid': len(valid) > 0,
    }


def half_life(k: float) -> float:
    """Vida media de eliminación t½ = ln(2)/k  [h]"""
    return np.log(2) / k


def time_to_cmb(k: float, V_mL: float, A0_mg: float, CMB: float,
                gamma: Optional[float] = None) -> Optional[float]:
    """
    Tiempo aproximado hasta que la concentración cae por debajo de CMB
    en una dosis única. Retorna None si nunca cae.
    """
    r = simulate_single_dose(k=k, V_mL=V_mL, A0_mg=A0_mg, CMB=CMB,
                             gamma=gamma, t_end=48.0, dt=0.005)
    return r.t_below_cmb