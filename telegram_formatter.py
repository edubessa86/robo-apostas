# -*- coding: utf-8 -*-
"""Monta o relatório em HTML do Telegram e divide mensagens longas sem cortar tags."""

import html
from typing import Any, Dict, List


class TelegramFormatter:
    @staticmethod
    def _rotulo_selecao(selection: str, home: str, away: str) -> str:
        if selection == "Home":
            return f"Vitória {home}"
        if selection == "Away":
            return f"Vitória {away}"
        return "Empate"

    @classmethod
    def format_daily_report(cls, data_formatada: str, processed_matches: List[Dict[str, Any]]) -> str:
        blocos: List[str] = [
            f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS PRÉ-JOGO — {html.escape(data_formatada)}</b>\n"
            "<i>Disparo automático das 10:00 BRT (ancoragem na Pinnacle)</i>\n"
            "━━━━━━━━━━━━━━━━━━"
        ]

        entradas = []
        for pm in processed_matches:
            m = pm["match"]
            for res in pm["results"]:
                if res.status == "VALUE":
                    entradas.append((res.ev_percent, m, res))
        entradas.sort(key=lambda e: e[0], reverse=True)

        if not entradas:
            blocos.append(
                "⚪ <b>STATUS: PASS</b>\n"
                "Nenhuma oportunidade atingiu o critério de EV mínimo em relação à Pinnacle hoje.\n"
                "━━━━━━━━━━━━━━━━━━"
            )
        else:
            for _, m, res in entradas:
                casa, fora = m["home_team"], m["away_team"]
                blocos.append(
                    f"🏆 <b>{html.escape(casa)} x {html.escape(fora)}</b> ({html.escape(m['league'])})\n"
                    f"⏰ Horário: {html.escape(m['horario'])} BRT\n"
                    f"🎯 Entrada: <b>{html.escape(cls._rotulo_selecao(res.selection, casa, fora))}</b>\n"
                    f"🏦 Melhor odd: <b>{html.escape(str(res.best_bookmaker))} {res.best_odd:.2f}</b> | "
                    f"Odd justa (Pinnacle s/ margem): <b>{res.sharp_fair_odd:.2f}</b>\n"
                    f"💎 EV estimado: <b>+{res.ev_percent:.2f}%</b> | "
                    f"Stake sugerida: <b>{res.kelly_stake_percent:.2f}%</b> da banca\n"
                    "━━━━━━━━━━━━━━━━━━"
                )

        blocos.append(
            "⚠️ <b>GESTÃO DE BANCA:</b> stake sugerida por Kelly fracionado. O EV é estimado a partir "
            "da odd justa da Pinnacle (sem margem) e não garante resultado.\n"
            "🔞 +18 | Aposte com responsabilidade."
        )
        blocos.append(
            "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!\n"
            "https://superbet.onelink.me/Hqv6/03r54ds3"
        )
        return "\n\n".join(blocos)

    @staticmethod
    def split_message(texto: str, limite: int = 3900) -> List[str]:
        """Divide por blocos (linha em branco) para não cortar tags HTML no meio."""
        partes, atual = [], ""
        for bloco in texto.split("\n\n"):
            candidato = f"{atual}\n\n{bloco}" if atual else bloco
            if len(candidato) <= limite:
                atual = candidato
            else:
                if atual:
                    partes.append(atual)
                atual = bloco
        if atual:
            partes.append(atual)
        return partes
