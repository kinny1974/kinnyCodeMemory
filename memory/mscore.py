"""
M_score — Fórmula de relevancia de memorias con decaimiento Ebbinghaus.

Implementa la fórmula de decaimiento exponencial para relevancia de memorias
basada en la curva de olvido de Ebbinghaus (Sprint 4):

    M_score = S_sim × e^(-λt) + w_freq × freq

Donde:
    S_sim  = similitud de coseno entre prompt actual y vector de memoria
    λ      = coeficiente de atenuación (lambda_days en días)
    t      = días transcurridos desde último acceso
    freq   = frecuencia acumulada de accesos
    w_freq = peso de frecuencia
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

# ── Pure Functions ──────────────────────────────────────────────────────


def decay_factor(lambda_days: float = 30.0, t_days: float = 0.0) -> float:
    """Calcular e^(-λt) donde λ=1/lambda_days, t=t_days.

    El coeficiente λ se deriva como el inverso de lambda_days, de modo que
    a t = lambda_days el factor cae a e^(-1) ≈ 0.368 (un e-fold).

    Args:
        lambda_days: Constante de decaimiento en días
            (Ebbinghaus default: 30).
        t_days: Días transcurridos desde último acceso.

    Returns:
        Factor de decaimiento entre 0.0 y 1.0.
    """
    if lambda_days <= 0:
        raise ValueError("lambda_days must be positive")
    if t_days < 0:
        raise ValueError("t_days must be non-negative")
    lam = 1.0 / lambda_days
    return math.exp(-lam * t_days)


def calculate_m_score(
    similarity: float,
    days_since_access: float,
    access_frequency: int = 0,
    lambda_days: float = 30.0,
    w_freq: float = 0.5,
) -> float:
    """Calcular la puntuación M_score de una memoria.

    Implementa la fórmula: M_score = S_sim × e^(-λt) + w_freq × freq

    Args:
        similarity: Similitud de coseno (0.0 a 1.0).
        days_since_access: Días desde último acceso.
        access_frequency: Número de accesos acumulados.
        lambda_days: Constante de decaimiento Ebbinghaus.
        w_freq: Peso del factor de frecuencia.

    Returns:
        M_score normalizado (0.0 a 1.0, puede superar ligeramente 1.0
        si freq es alto).
    """
    if not (0.0 <= similarity <= 1.0):
        raise ValueError("similarity must be between 0.0 and 1.0")
    if days_since_access < 0:
        raise ValueError("days_since_access must be non-negative")
    if access_frequency < 0:
        raise ValueError("access_frequency must be non-negative")
    if w_freq < 0:
        raise ValueError("w_freq must be non-negative")

    return similarity * decay_factor(lambda_days, days_since_access) + w_freq * access_frequency


# ── MemoryRelevanceManager ──────────────────────────────────────────────


class MemoryRelevanceManager:
    """Gestiona la relevancia de memorias con decaimiento Ebbinghaus.

    Mantiene un índice local de accesos (timestamp y frecuencia) para cada
    memory_id, permitiendo calcular M_score dinámico sin persistencia en DB.
    El estado se puede serializar a JSON con persist_state() / load_state().

    Ejemplo:
        >>> mgr = MemoryRelevanceManager(lambda_days=30, w_freq=0.5)
        >>> mgr.record_access("mem_1")
        >>> mgr.record_access("mem_1")
        >>> mgr.get_score("mem_1", similarity=0.8)
        0.8 * e^0 + 0.5 * 2 = 1.8
    """

    def __init__(
        self,
        lambda_days: float = 30.0,
        w_freq: float = 0.5,
    ) -> None:
        """Inicializar el gestor con parámetros de decaimiento.

        Args:
            lambda_days: Constante de decaimiento en días (default 30).
            w_freq: Peso del factor de frecuencia (default 0.5).
        """
        self.lambda_days = lambda_days
        self.w_freq = w_freq
        # memory_id -> {"last_access_ts": float, "access_count": int}
        self._registry: dict[str, dict[str, Any]] = {}

    # ── Access tracking ─────────────────────────────────────────────

    def record_access(self, memory_id: str) -> None:
        """Registrar un acceso a una memoria.

        Incrementa el contador de accesos y actualiza el timestamp
        del último acceso. Si la memoria no existe en el registro,
        se crea con access_count=1.

        Args:
            memory_id: Identificador único de la memoria.
        """
        now = time.time()
        if memory_id in self._registry:
            entry = self._registry[memory_id]
            entry["last_access_ts"] = now
            entry["access_count"] += 1
        else:
            self._registry[memory_id] = {
                "last_access_ts": now,
                "access_count": 1,
            }

    def get_recent_access(self, memory_id: str) -> float:
        """Obtener días transcurridos desde el último acceso.

        Args:
            memory_id: Identificador único de la memoria.

        Returns:
            Días fraccionarios desde el último acceso (0.0 si no registrado).
        """
        if memory_id not in self._registry:
            return 0.0
        now = time.time()
        seconds = now - self._registry[memory_id]["last_access_ts"]
        return seconds / 86400.0

    def get_access_count(self, memory_id: str) -> int:
        """Obtener conteo de accesos acumulados.

        Args:
            memory_id: Identificador único de la memoria.

        Returns:
            Número de accesos registrados (0 si no existe).
        """
        if memory_id not in self._registry:
            return 0
        return self._registry[memory_id]["access_count"]

    # ── Scoring ─────────────────────────────────────────────────────

    def get_score(
        self,
        memory_id: str,
        similarity: float,
    ) -> float:
        """Calcular M_score para una memoria específica.

        Integra similitud, decaimiento temporal y frecuencia de acceso
        usando los parámetros del gestor.

        Args:
            memory_id: Identificador único de la memoria.
            similarity: Similitud de coseno (0.0 a 1.0).

        Returns:
            M_score combinado.
        """
        days = self.get_recent_access(memory_id)
        freq = self.get_access_count(memory_id)
        return calculate_m_score(
            similarity=similarity,
            days_since_access=days,
            access_frequency=freq,
            lambda_days=self.lambda_days,
            w_freq=self.w_freq,
        )

    # ── Batch operations ────────────────────────────────────────────

    def consolidate_scores(self, memories: list[dict]) -> list[dict]:
        """Dado un listado de memorias con sus scores, reordenar por score descendente.

        Añade un campo ``m_score`` a cada entrada usando los datos
        internos del gestor (accesos y frecuencias) junto con la
        similitud proporcionada.

        Args:
            memories: Lista de dicts con al menos
                ``{"memory_id": str, "similarity": float}`` y campos
                adicionales que se propagan tal cual.

        Returns:
            Lista ordenada por ``m_score`` descendente, añadiendo el
            campo ``m_score`` a cada entrada.
        """
        scored: list[dict] = []
        for mem in memories:
            mid = mem["memory_id"]
            sim = mem.get("similarity", 0.0)
            m_score = self.get_score(mid, sim)
            entry = dict(mem)
            entry["m_score"] = m_score
            scored.append(entry)
        scored.sort(key=lambda e: e["m_score"], reverse=True)
        return scored

    # ── Persistence ─────────────────────────────────────────────────

    def persist_state(self, path: str) -> None:
        """Persistir el estado (accesos y frecuencias) a JSON.

        Args:
            path: Ruta al archivo JSON de salida.
        """
        p = Path(path)
        data = {
            "lambda_days": self.lambda_days,
            "w_freq": self.w_freq,
            "registry": {
                mid: {
                    "last_access_ts": entry["last_access_ts"],
                    "access_count": entry["access_count"],
                }
                for mid, entry in self._registry.items()
            },
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))

    def load_state(self, path: str) -> None:
        """Cargar estado desde JSON.

        Sobrescribe el estado actual del gestor con los datos
        del archivo. Si el archivo no existe, se deja el
        gestor vacío (sin error).

        Args:
            path: Ruta al archivo JSON de entrada.
        """
        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text())
        self.lambda_days = data.get("lambda_days", 30.0)
        self.w_freq = data.get("w_freq", 0.5)
        self._registry = {mid: entry for mid, entry in data.get("registry", {}).items()}

    # ── Introspection ───────────────────────────────────────────────

    @property
    def memory_ids(self) -> set[str]:
        """Conjunto de IDs de memorias registradas."""
        return set(self._registry.keys())

    @property
    def count(self) -> int:
        """Número de memorias registradas."""
        return len(self._registry)

    def clear(self) -> None:
        """Eliminar todas las memorias del registro."""
        self._registry.clear()
