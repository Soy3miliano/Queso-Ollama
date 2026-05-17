"""
notifier.py
"""

import threading
import time
import platform
import subprocess
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from win10toast import ToastNotifier
    _HAS_WIN10TOAST = True
except ImportError:
    _HAS_WIN10TOAST = False

# ──────────────────────────────────────────────
# Detección de plataforma
# ──────────────────────────────────────────────

_PLATFORM = platform.system()          # "Windows" | "Darwin" | "Linux"


def _notify_windows(title: str, message: str) -> None:
    # Notificación nativa en Windows vía PowerShell 
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f"$n.ShowBalloonTip(8000, '{title}', '{message}', "
        "[System.Windows.Forms.ToolTipIcon]::Info); "
        "Start-Sleep -Seconds 9; "
        "$n.Dispose()"
    )
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _notify_macos(title: str, message: str) -> None:
    # Notificación nativa en macOS vía osascript
    script = (
        f'display notification "{message}" '
        f'with title "{title}" '
        f'sound name "Ping"'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def _notify_linux(title: str, message: str) -> None:
    # Notificación en Linux
    try:
        subprocess.run(
            ["notify-send", "--urgency=critical", "--expire-time=10000",
             title, message],
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback: alerta en terminal con beep ASCII
        print(f"\a\n{'='*50}\n⚠  {title}\n   {message}\n{'='*50}\n")


def _notify_win10toast(title: str, message: str) -> None:
    notifier = ToastNotifier()
    notifier.show_toast(title, message, duration=10, threaded=True)


def notify(title: str, message: str) -> None:
    """
    Dispara una notificación nativa en el sistema operativo actual.
    Args:
        title   : Título del popup
        message : Cuerpo del mensaje
    """
    print(f"[NOTIFICACIÓN] Intentando enviar: {title} — {message}")
    try:
        if _PLATFORM == "Windows":
            try:
                _notify_windows(title, message)
                logger.info("Notificación Windows enviada via PowerShell: %s", title)
                print(f"[NOTIFICACIÓN] Enviada via PowerShell: {title}")
            except Exception as exc:
                logger.warning("PowerShell notification failed: %s", exc)
                print(f"[NOTIFICACIÓN] PowerShell falló, intentando win10toast...")
                if _HAS_WIN10TOAST:
                    _notify_win10toast(title, message)
                    logger.info("Notificación Windows enviada via win10toast: %s", title)
                    print(f"[NOTIFICACIÓN] Enviada via win10toast: {title}")
                else:
                    raise
        elif _PLATFORM == "Darwin":
            _notify_macos(title, message)
        else:
            _notify_linux(title, message)
    except Exception as exc:
        logger.warning("No se pudo mostrar notificación: %s", exc)
        print(f"[RECORDATORIO] {title}: {message}")
        if _PLATFORM == "Windows" and _HAS_WIN10TOAST:
            try:
                _notify_win10toast(title, message)
                logger.info("Notificación Windows enviada via win10toast fallback: %s", title)
            except Exception as toast_exc:
                logger.warning("win10toast fallback también falló: %s", toast_exc)

# Programador de recordatorios

@dataclass
class DoseSchedule:
    # Configuración de un esquema de dosificación activo.
    drug_name: str
    dose_mg: float
    interval_h: float
    total_hours: float              # duración total del tratamiento [h]
    start_time: datetime = field(default_factory=datetime.now)
    first_dose_time: Optional[datetime] = None
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _dose_times: list[datetime] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.first_dose_time is None:
            first_time = self.start_time
        else:
            first_time = self.first_dose_time
            if first_time < self.start_time:
                elapsed = self.start_time - first_time
                interval_seconds = self.interval_h * 3600
                doses_skipped = int(elapsed.total_seconds() // interval_seconds)
                first_time = first_time + timedelta(seconds=doses_skipped * interval_seconds)
                if first_time < self.start_time:
                    first_time += timedelta(hours=self.interval_h)

        num_doses = max(1, int(self.total_hours / self.interval_h) + 1)
        self._dose_times = [
            first_time + timedelta(hours=i * self.interval_h)
            for i in range(num_doses)
        ]

    @property
    def next_dose_time(self) -> Optional[datetime]:
        now = datetime.now()
        for dt in self._dose_times:
            if dt >= now:
                return dt
        return None

    @property
    def remaining_doses(self) -> int:
        now = datetime.now()
        return sum(1 for dt in self._dose_times if dt >= now)

    @property
    def dose_times(self) -> list[datetime]:
        return list(self._dose_times)

    def cancel(self) -> None:
        """Detiene el recordatorio."""
        self._stop_event.set()


# Registro global de recordatorios activos
_active_schedules: list[DoseSchedule] = []
_lock = threading.Lock()


def _reminder_loop(schedule: DoseSchedule) -> None:
    # Loop interno que corre en un thread secundario.
    dose_times = schedule.dose_times
    total_doses = len(dose_times)

    for dose_index, scheduled_time in enumerate(dose_times, start=1):
        if schedule._stop_event.is_set():
            break

        now = datetime.now()
        wait_seconds = max(0.0, (scheduled_time - now).total_seconds())

        if schedule._stop_event.wait(timeout=wait_seconds):
            break

        _fire_dose_notification(schedule, dose_index)

        if dose_index == total_doses:
            _fire_end_notification(schedule)


def _fire_dose_notification(schedule: DoseSchedule, dose_num: int) -> None:
    next_time = schedule.next_dose_time
    title = f"💊 Hora de tu {schedule.drug_name}"
    if next_time and next_time > datetime.now():
        next_str = next_time.strftime('%H:%M')
        message = (
            f"Dosis #{dose_num} — {schedule.dose_mg:.0f} mg\n"
            f"Próxima dosis a las {next_str}"
        )
    else:
        message = (
            f"Dosis #{dose_num} — {schedule.dose_mg:.0f} mg\n"
            "Esta es la dosis actual."
        )
    notify(title, message)
    logger.info("Recordatorio enviado: %s dosis #%d", schedule.drug_name, dose_num)


def _fire_end_notification(schedule: DoseSchedule) -> None:
    notify(
        title=f"✅ Tratamiento completado — {schedule.drug_name}",
        message="Has completado el ciclo de dosificación. "
                "Consulta a tu médico si los síntomas persisten.",
    )


def schedule_reminders(
    drug_name: str,
    dose_mg: float,
    interval_h: float,
    total_hours: float = 48.0,
    first_dose_time: Optional[datetime] = None,
) -> DoseSchedule:
    """
    Programa recordatorios periódicos para un fármaco.

    Args:
        drug_name   : nombre del medicamento
        dose_mg     : dosis por toma [mg]
        interval_h  : intervalo entre dosis [h]
        total_hours : duración total del tratamiento [h]

    Returns:
        DoseSchedule activo (cancelable con .cancel())
    """
    schedule = DoseSchedule(
        drug_name=drug_name,
        dose_mg=dose_mg,
        interval_h=interval_h,
        total_hours=total_hours,
        first_dose_time=first_dose_time,
    )

    thread = threading.Thread(
        target=_reminder_loop,
        args=(schedule,),
        daemon=True,        # muere con el proceso principal
        name=f"DoseReminder-{drug_name}",
    )
    schedule._thread = thread

    with _lock:
        _active_schedules.append(schedule)

    thread.start()
    logger.info(
        "Recordatorios programados: %s — cada %.1f h durante %.0f h",
        drug_name, interval_h, total_hours,
    )
    return schedule


def cancel_all() -> int:
    """
    Cancela todos los recordatorios activos.

    Returns:
        Número de recordatorios cancelados.
    """
    with _lock:
        count = len(_active_schedules)
        for s in _active_schedules:
            s.cancel()
        _active_schedules.clear()
    return count


def list_active() -> list[dict]:
    """Retorna una lista de los recordatorios activos."""
    with _lock:
        return [
            {
                "drug": s.drug_name,
                "dose_mg": s.dose_mg,
                "interval_h": s.interval_h,
                "started": s.start_time.strftime("%Y-%m-%d %H:%M"),
                "next_dose_at": s.next_dose_time.strftime("%Y-%m-%d %H:%M") if s.next_dose_time else None,
                "remaining_doses": s.remaining_doses,
            }
            for s in _active_schedules
        ]