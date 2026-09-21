# -*- coding: utf-8 -*-
"""Camada SQLite: registra partidas e sinais de VALOR para auditoria posterior (CLV).

ATENÇÃO (GitHub Actions): o runner é descartado ao fim de cada execução, então o
arquivo .db some junto. Para acumular histórico entre dias, persista o arquivo
(actions/cache, artifact ou commit do .db de volta ao repositório).
"""

import os
import sqlite3
from typing import Any, Dict, Optional


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.getenv("DB_PATH", "robo_apostas.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id  TEXT NOT NULL UNIQUE,
                league       TEXT,
                home_team    TEXT,
                away_team    TEXT,
                start_time   TEXT,
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS signals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id         INTEGER NOT NULL REFERENCES matches(id),
                bookmaker        TEXT NOT NULL,
                market           TEXT NOT NULL,
                selection        TEXT NOT NULL,
                entry_odd        REAL NOT NULL,
                fair_odd_sharp   REAL NOT NULL,
                fair_prob        REAL NOT NULL,
                price_edge       REAL,
                ev               REAL,
                kelly_stake      REAL,
                closing_odd_sharp REAL,   -- preencher depois (auditoria de CLV)
                clv              REAL,    -- preencher depois
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (match_id, bookmaker, market, selection)
            );
            """
        )
        self.conn.commit()

    def log_match(self, external_id: str, league: str, home: str, away: str, start_time: str) -> int:
        """Insere ou atualiza a partida e devolve o id interno."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO matches (external_id, league, home_team, away_team, start_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    league = excluded.league,
                    home_team = excluded.home_team,
                    away_team = excluded.away_team,
                    start_time = excluded.start_time
                """,
                (external_id, league, home, away, start_time),
            )
        row = self.conn.execute(
            "SELECT id FROM matches WHERE external_id = ?", (external_id,)
        ).fetchone()
        return int(row[0])

    def log_signal(self, signal: Dict[str, Any]) -> bool:
        """Grava um sinal. Retorna False se ele já existia (reexecução no mesmo dia)."""
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO signals
                    (match_id, bookmaker, market, selection, entry_odd,
                     fair_odd_sharp, fair_prob, price_edge, ev, kelly_stake)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["match_id"], signal["bookmaker"], signal["market"],
                    signal["selection"], signal["entry_odd"], signal["fair_odd_sharp"],
                    signal["fair_prob"], signal["price_edge"], signal["ev"],
                    signal["kelly_stake"],
                ),
            )
        return cur.rowcount > 0

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
