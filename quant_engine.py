# -*- coding: utf-8 -*-
"""Motor quantitativo: remove a margem da Pinnacle, faz line shopping entre as casas
comerciais e classifica cada resultado do 1X2."""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SELECTIONS = ("Home", "Draw", "Away")


@dataclass
class MarketResult:
    selection: str
    status: str  # VALUE | NO_VALUE | NO_ODDS | SUSPICIOUS_EDGE | STALE_DATA | INVALID_DATA
    best_bookmaker: Optional[str] = None
    best_odd: float = 0.0
    sharp_fair_odd: float = 0.0
    sharp_fair_prob: float = 0.0
    price_edge_percent: float = 0.0
    ev_percent: float = 0.0
    kelly_stake_percent: float = 0.0
    note: str = ""


def _odd_valida(v: Any) -> bool:
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(v)
        and v > 1.0
    )


class QuantEngine:
    def __init__(
        self,
        min_ev: float = 0.03,
        min_price_edge: float = 0.03,
        max_data_age_seconds: int = 180,
        max_ev: float = 0.15,              # acima disso o "valor" é suspeito (odd velha, jogo pareado errado)
        max_sharp_overround: float = 1.10, # margem da Pinnacle acima disso indica dado ruim
        kelly_fraction: float = 0.25,      # Kelly fracionado (¼)
        max_stake_pct: float = 2.0,        # teto de stake, em % da banca
    ) -> None:
        self.min_ev = min_ev
        self.min_price_edge = min_price_edge
        self.max_data_age_seconds = max_data_age_seconds
        self.max_ev = max_ev
        self.max_sharp_overround = max_sharp_overround
        self.kelly_fraction = kelly_fraction
        self.max_stake_pct = max_stake_pct

    # ------------------------------------------------------------------ de-vig
    def remove_vig_proportional(self, odds_1x2: Dict[str, float]) -> Optional[Dict[str, float]]:
        """Probabilidades justas (sem margem). Exige exatamente Home, Draw e Away."""
        if not isinstance(odds_1x2, dict) or set(odds_1x2) != set(SELECTIONS):
            return None
        if not all(_odd_valida(odds_1x2[k]) for k in SELECTIONS):
            return None
        implied = {k: 1.0 / float(odds_1x2[k]) for k in SELECTIONS}
        overround = sum(implied.values())
        if overround <= 1.0 or overround > self.max_sharp_overround:
            return None
        return {k: p / overround for k, p in implied.items()}

    # --------------------------------------------------------------- avaliação
    def _todos(self, status: str, note: str) -> List[MarketResult]:
        return [MarketResult(selection=s, status=status, note=note) for s in SELECTIONS]

    def evaluate_match_market(
        self,
        sharp_odds_1x2: Dict[str, float],
        commercial_odds_multi_book: Dict[str, Dict[str, float]],
        last_update_utc: Optional[datetime],
        now_utc: Optional[datetime] = None,
    ) -> List[MarketResult]:
        now_utc = now_utc or datetime.now(timezone.utc)

        if last_update_utc is None or last_update_utc.tzinfo is None:
            return self._todos("INVALID_DATA", "timestamp das odds ausente ou sem fuso horário")
        idade = (now_utc - last_update_utc).total_seconds()
        if idade < -60:
            return self._todos("INVALID_DATA", "timestamp das odds está no futuro")
        if idade > self.max_data_age_seconds:
            return self._todos("STALE_DATA", f"odds com {idade:.0f}s (limite {self.max_data_age_seconds}s)")

        fair = self.remove_vig_proportional(sharp_odds_1x2)
        if fair is None:
            return self._todos("INVALID_DATA", "odds da Pinnacle inválidas (chaves, valores ou margem)")

        return [self._avaliar_selecao(s, fair[s], commercial_odds_multi_book) for s in SELECTIONS]

    def _avaliar_selecao(
        self, selection: str, fair_prob: float, commercial: Dict[str, Dict[str, float]]
    ) -> MarketResult:
        best_book, best_odd = None, 0.0
        for book, odds in (commercial or {}).items():
            if not isinstance(odds, dict):
                continue
            o = odds.get(selection)
            if _odd_valida(o) and o > best_odd:  # line shopping: melhor odd entre as casas
                best_book, best_odd = book, float(o)

        fair_odd = 1.0 / fair_prob
        if best_book is None:
            return MarketResult(selection, "NO_ODDS", sharp_fair_odd=round(fair_odd, 3),
                                sharp_fair_prob=round(fair_prob, 4), note="nenhuma casa com odd válida")

        ev = fair_prob * best_odd - 1.0
        # Observação: price_edge (odd/odd_justa - 1) é matematicamente igual ao EV
        # quando ambos usam a mesma probabilidade justa. Os dois campos são mantidos
        # por compatibilidade com o banco, mas o relatório exibe apenas o EV.
        price_edge = best_odd / fair_odd - 1.0

        if ev >= self.min_ev and price_edge >= self.min_price_edge:
            status = "SUSPICIOUS_EDGE" if ev > self.max_ev else "VALUE"
        else:
            status = "NO_VALUE"

        kelly = 0.0
        if status == "VALUE":
            full_kelly = ev / (best_odd - 1.0)
            kelly = min(full_kelly * self.kelly_fraction * 100.0, self.max_stake_pct)

        return MarketResult(
            selection=selection,
            status=status,
            best_bookmaker=best_book,
            best_odd=best_odd,
            sharp_fair_odd=round(fair_odd, 3),
            sharp_fair_prob=round(fair_prob, 4),
            price_edge_percent=round(price_edge * 100.0, 2),
            ev_percent=round(ev * 100.0, 2),
            kelly_stake_percent=round(kelly, 2),
            note="edge acima do teto: confira odds e pareamento dos jogos" if status == "SUSPICIOUS_EDGE" else "",
        )
