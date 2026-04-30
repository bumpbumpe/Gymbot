import re
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_cycle_workout(text: str) -> tuple[Optional[int], Optional[int]]:
    """Цикл 21 Тренировка 3  →  (21, 3)"""
    m = re.search(r"цикл\s*(\d+).*?тренировка\s*(\d+)", text, re.I | re.S)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _extract_fatigue_expectation(text: str) -> Optional[str]:
    """Ожидаемый уровень усталости - 6-8  →  '6-8'"""
    m = re.search(r"уровень усталости[^\d]*(\d+[\-–]\d+|\d+)", text, re.I)
    return m.group(1) if m else None


def _extract_fatigue_result(text: str) -> Optional[str]:
    """След ур усталости\n6/10  →  '6/10'"""
    m = re.search(r"след[а-я.]*\s+ур[а-я.]*\s+усталост[а-я]*\s*\n\s*(\d+/10)", text, re.I)
    if m:
        return m.group(1)
    # fallback: last X/10 in text
    all_rpe = re.findall(r"\b(\d+)/10\b", text)
    return all_rpe[-1] if all_rpe else None


def _split_into_exercise_blocks(text: str) -> list[str]:
    """
    Split message into exercise blocks.
    Each block starts with a non-numeric line (exercise name) followed by set lines.
    """
    lines = text.split("\n")
    blocks = []
    current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Service lines to skip
        skip_patterns = [
            r"^цикл\s*\d+",
            r"^тренировка\s*\d+",
            r"^ожидаемый",
            r"^разминка",
            r"^след",
        ]
        if any(re.match(p, stripped, re.I) for p in skip_patterns):
            if current:
                blocks.append("\n".join(current))
                current = []
            continue

        current.append(stripped)

    if current:
        blocks.append("\n".join(current))

    return [b for b in blocks if b.strip()]


def _parse_sets(block_lines: list[str]) -> list[dict]:
    """
    Parse set lines like:
      85 х 1-2 х 3       → weight=85, reps='1-2', sets=3
      65 х 9 х 2          → weight=65, reps=9, sets=2
      10х10 с виса        → weight=10, reps=10, sets=1  (bodyweight/notes preserved)
      5 х 12 х 5          → weight=5, reps=12, sets=5
    """
    sets = []
    # Pattern: [weight] x [reps] x [sets]  (all separators: х, x, ×)
    sep = r"[хxх×]"
    p3 = re.compile(
        rf"^([\d.,]+)\s*{sep}\s*([\d.\-–]+(?:\+[\d]+)?)\s*{sep}\s*([\d]+)", re.I
    )
    p2 = re.compile(rf"^([\d.,]+)\s*{sep}\s*([\d.\-–]+(?:\+[\d]+)?)", re.I)

    for line in block_lines:
        line = line.strip()
        if not line:
            continue
        # skip RPE lines
        if re.match(r"^\d+/10", line):
            continue

        m3 = p3.match(line)
        if m3:
            sets.append({
                "weight": float(m3.group(1).replace(",", ".")),
                "reps": m3.group(2),
                "sets": int(m3.group(3)),
                "raw": line,
            })
            continue

        m2 = p2.match(line)
        if m2:
            sets.append({
                "weight": float(m2.group(1).replace(",", ".")),
                "reps": m2.group(2),
                "sets": 1,
                "raw": line,
            })

    return sets


def _extract_rpe(block: str) -> Optional[str]:
    """Find X/10 RPE in block."""
    m = re.search(r"\b(\d+)/10\b", block)
    return m.group(1) if m else None


def _extract_exercise_name(first_line: str) -> str:
    """Clean exercise name from first line of block."""
    # Remove trailing set notation if accidentally included
    name = re.sub(r"\s*\d+[\s\-х].*$", "", first_line).strip()
    return name if name else first_line.strip()


def _parse_exercises_from_blocks(blocks: list[str]) -> list[dict]:
    exercises = []
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        # First line = exercise name (unless it looks like a set)
        sep = r"[хxх×]"
        if re.match(rf"^\d+\s*{sep}", lines[0], re.I):
            # whole block is sets, no name → skip or use previous
            continue

        name = _extract_exercise_name(lines[0])
        set_lines = lines[1:]
        sets = _parse_sets(set_lines)
        rpe_raw = _extract_rpe(block)

        # Compute working set = last heavy set (max weight)
        working_weight = None
        if sets:
            working_weight = max(s["weight"] for s in sets)

        exercises.append({
            "name": name,
            "sets": sets,
            "working_weight": working_weight,
            "rpe": rpe_raw,
        })

    return exercises


# ── public API ────────────────────────────────────────────────────────────────

def parse_trainer_message(text: str) -> Optional[dict]:
    """
    Parse trainer's workout plan message.
    Returns dict or None if not a workout plan.
    """
    cycle, workout = _extract_cycle_workout(text)
    if not cycle:
        return None

    blocks = _split_into_exercise_blocks(text)
    exercises = _parse_exercises_from_blocks(blocks)

    return {
        "type": "plan",
        "cycle": cycle,
        "workout": workout,
        "expected_fatigue": _extract_fatigue_expectation(text),
        "exercises": exercises,
        "raw": text,
    }


def parse_athlete_message(text: str) -> Optional[dict]:
    """
    Parse athlete's result message.
    Returns dict or None if not a workout result.
    """
    cycle, workout = _extract_cycle_workout(text)
    if not cycle:
        return None

    # Must have at least one X/10 to be a result (not a forwarded plan)
    if not re.search(r"\b\d+/10\b", text):
        return None

    blocks = _split_into_exercise_blocks(text)
    exercises = _parse_exercises_from_blocks(blocks)

    fatigue = _extract_fatigue_result(text)

    return {
        "type": "result",
        "cycle": cycle,
        "workout": workout,
        "fatigue": fatigue,
        "exercises": exercises,
        "raw": text,
    }
