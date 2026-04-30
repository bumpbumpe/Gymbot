import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional
import os

DB_PATH = os.environ.get("DB_PATH", "gym.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS workout_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle INTEGER,
            workout INTEGER,
            expected_fatigue TEXT,
            date TEXT,
            raw TEXT
        );

        CREATE TABLE IF NOT EXISTS exercise_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER REFERENCES workout_plans(id),
            name TEXT,
            sets_json TEXT,
            working_weight REAL
        );

        CREATE TABLE IF NOT EXISTS workout_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle INTEGER,
            workout INTEGER,
            fatigue TEXT,
            date TEXT,
            athlete TEXT,
            raw TEXT
        );

        CREATE TABLE IF NOT EXISTS exercise_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER REFERENCES workout_results(id),
            name TEXT,
            name_normalized TEXT,
            sets_json TEXT,
            working_weight REAL,
            rpe TEXT,
            date TEXT
        );
    """)
    conn.commit()
    conn.close()


def _normalize_name(name: str) -> str:
    """Simple normalization for fuzzy search."""
    import re
    n = name.lower().strip()
    n = re.sub(r"\s+", " ", n)
    return n


def save_workout_plan(plan: dict, date: datetime):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO workout_plans (cycle, workout, expected_fatigue, date, raw) VALUES (?,?,?,?,?)",
        (plan["cycle"], plan["workout"], plan.get("expected_fatigue"), date.isoformat(), plan["raw"])
    )
    plan_id = c.lastrowid
    for ex in plan.get("exercises", []):
        c.execute(
            "INSERT INTO exercise_plans (plan_id, name, sets_json, working_weight) VALUES (?,?,?,?)",
            (plan_id, ex["name"], json.dumps(ex["sets"], ensure_ascii=False), ex.get("working_weight"))
        )
    conn.commit()
    conn.close()


def save_workout_result(result: dict, date: datetime, athlete: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO workout_results (cycle, workout, fatigue, date, athlete, raw) VALUES (?,?,?,?,?,?)",
        (result["cycle"], result["workout"], result.get("fatigue"), date.isoformat(), athlete, result["raw"])
    )
    result_id = c.lastrowid
    for ex in result.get("exercises", []):
        c.execute(
            """INSERT INTO exercise_results
               (result_id, name, name_normalized, sets_json, working_weight, rpe, date)
               VALUES (?,?,?,?,?,?,?)""",
            (
                result_id,
                ex["name"],
                _normalize_name(ex["name"]),
                json.dumps(ex["sets"], ensure_ascii=False),
                ex.get("working_weight"),
                ex.get("rpe"),
                date.isoformat(),
            )
        )
    conn.commit()
    conn.close()


def get_exercises_list() -> list[str]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT name, COUNT(*) as cnt
        FROM exercise_results
        GROUP BY name_normalized
        ORDER BY cnt DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [r["name"] for r in rows]


def get_exercise_history(query: str, period: str = "all") -> list[dict]:
    """
    Fuzzy search exercise by name, return history filtered by period.
    period: week | month | quarter | halfyear | year | all
    """
    conn = get_conn()
    c = conn.cursor()

    # Date filter
    now = datetime.utcnow()
    period_map = {
        "week": 7,
        "month": 30,
        "quarter": 90,
        "halfyear": 180,
        "year": 365,
    }
    days = period_map.get(period)
    date_filter = ""
    params = [f"%{query.lower()}%"]
    if days:
        from_date = (now - timedelta(days=days)).isoformat()
        date_filter = "AND date >= ?"
        params.append(from_date)

    c.execute(f"""
        SELECT date, name, working_weight, rpe, sets_json
        FROM exercise_results
        WHERE name_normalized LIKE ?
        {date_filter}
        ORDER BY date ASC
    """, params)

    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "date": r["date"][:10],
            "name": r["name"],
            "weight": r["working_weight"],
            "rpe": float(r["rpe"]) if r["rpe"] else None,
            "sets": json.loads(r["sets_json"]) if r["sets_json"] else [],
        })
    return result


def get_recent_stats(days: int = 30) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

    c.execute("""
        SELECT
            name,
            name_normalized,
            COUNT(DISTINCT result_id) as sessions,
            MAX(working_weight) as max_weight,
            AVG(CAST(rpe AS REAL)) as avg_rpe
        FROM exercise_results
        WHERE date >= ? AND working_weight IS NOT NULL
        GROUP BY name_normalized
        ORDER BY sessions DESC
        LIMIT 10
    """, (from_date,))

    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
