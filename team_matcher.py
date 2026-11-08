#!/usr/bin/env python3
"""
team_matcher.py — сопоставление заголовка VK-видео с официальным матчем.

Главная идея: вместо поиска точного названия команды в общем справочнике
(сотни вариантов написания) берём ОФИЦИАЛЬНЫЕ матчи нужной даты (обычно
5-15 штук) и выбираем тот, у которого в заголовке нашлись ОБЕ команды.

Сравнение идёт по "скелету" названия: регистр, ё/е, кавычки, ХК/ЖХК, №,
пробелы и дефисы не важны. Поэтому "ГУД ГОЛ" = "ГудГол",
"ЗВЕЗДА ЮГО ЗАПАД" = "Звезда Юго-Запад", "СШОР 1" = "СШ №1" (через
группы синонимов), "ДИНАМО-ЮНИОР" = "Динамо Юниор".

Защиты от ложных совпадений:
  * команда не должна "обрываться" посреди более длинного названия
    ("СКА" не совпадёт внутри "СКА Хкд" или "СКА Петергоф");
  * номер состава учитывается ("Юниор 2" не совпадёт с "Юниор");
  * если возраст указан в заголовке, матч другого возраста отбрасывается;
  * если подходят два разных матча одинаково хорошо — результат считается
    неоднозначным, видео уходит на ручную проверку;
  * обзоры/нарезки не сопоставляются вообще.

Модуль ничего не пишет на диск и не ходит в сеть — только читает файлы
расписания, поэтому его можно безопасно тестировать отдельно
(см. test_team_matcher.py).
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
OFFICIAL_KEYS_FILE = BASE_DIR / "official_matches.json"      # есть уже сейчас (без возрастов)
FIXTURES_FILE = BASE_DIR / "official_fixtures.json"          # появится на этапе 2 (с возрастами)
ALIASES_FILE = BASE_DIR / "team_aliases.json"                # необязательный, для новых синонимов

SEP = "|"

# Группы синонимов: любое название группы считается тем же клубом.
# Новые синонимы можно добавлять в team_aliases.json (список списков),
# не меняя код.
DEFAULT_ALIAS_GROUPS = [
    ["ска петергоф", "петергоф"],
    ["сш 1", "сшор 1"],
    ["московская академия хоккея", "мах"],
    ["красная машина юниор", "красная машина", "кмю"],
    ["красная машина юниор 2", "красная машина 2", "кмю 2"],
    ["динамо форвард", "форвард"],
]

REVIEW_WORDS = ("обзор", "хайлайт", "highlight", "лучшие моменты",
                "голевые моменты", "нарезка")

# Слова, которые могут стоять вплотную к названию команды, но сами
# названием не являются.
NOISE_TOKENS = {
    "хк", "жхк", "мхк", "матч", "матча", "игра", "кубок", "кубка",
    "первенство", "первенства", "спб", "федерации", "россии", "турнир",
    "хоккей", "сезон", "начало", "в", "на", "арена", "хорс", "трансляция",
    "live", "товарищеская", "товарищеский", "контрольный", "контрольная",
    "мск", "москва", "г", "р", "гр", "год", "года", "i", "ii", "iii",
    "финал", "полуфинал", "тур", "группа",
}

_SEPARATORS_RE = re.compile(r"🆚|\bvs\b|&|/|\||—|–|×")
_INNER_HYPHEN_RE = re.compile(r"(?<=[a-zа-я])-\s?(?=[a-zа-я])")
_DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b")
_TIME_OR_SCORE_RE = re.compile(r"\b\d{1,2}\s*:\s*\d{1,2}\b")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_BIRTH_YEAR_RE = re.compile(r"\b20(09|1[0-8])\b")
_NON_TOKEN_RE = re.compile(r"[^a-zа-я0-9|]+")
_TWO_DIGIT_AGE_RE = re.compile(r"^(09|1[0-8])$")
_ROMAN_SQUAD = {"ii": "2", "iii": "3", "iv": "4"}   # одиночная "I" — разделитель, её не трогаем


# ---------------------------------------------------------------------------
# Токенизация
# ---------------------------------------------------------------------------

_LATIN_NUMBER_RE = re.compile(r"\bn(?=\s?\d)")    # "СШ N1" = "СШ №1"


def _prepare(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    t = _LATIN_NUMBER_RE.sub(" ", t)
    t = _DATE_RE.sub(" ", t)
    t = _TIME_OR_SCORE_RE.sub(" ", t)
    t = _SEPARATORS_RE.sub(f" {SEP} ", t)
    t = _INNER_HYPHEN_RE.sub(" ", t)      # "динамо-юниор" -> "динамо юниор"
    t = t.replace("-", f" {SEP} ")         # оставшиеся дефисы — разделитель команд
    return t


def tokenize_title(title: str):
    """Возвращает (токены, найденные_возрасты). Даты, время, счёт и годы
    рождения из токенов убираются; возраст запоминается отдельно."""
    t = _prepare(title)
    ages = list(_BIRTH_YEAR_RE.findall(t))   # "2016" -> "16"
    t = _YEAR_RE.sub(" ", t)
    t = _NON_TOKEN_RE.sub(" ", t)

    tokens = []
    for tok in t.split():
        tok = _ROMAN_SQUAD.get(tok, tok)          # "СКА-Звезда II" = второй состав
        if _TWO_DIGIT_AGE_RE.match(tok):
            ages.append(tok)
            continue
        if tok == SEP and tokens and tokens[-1] == SEP:
            continue
        tokens.append(tok)
    return tokens, ages


def tokenize_name(name: str) -> list:
    """Токены названия команды (из официального ключа или синонима)."""
    t = (name or "").lower().replace("ё", "е")
    t = _LATIN_NUMBER_RE.sub(" ", t)
    t = _INNER_HYPHEN_RE.sub(" ", t)
    t = t.replace("-", " ")
    t = _NON_TOKEN_RE.sub(" ", t)
    return [tok for tok in t.split() if tok not in ("хк", "жхк")]


def _skeleton(name: str) -> str:
    return "".join(tokenize_name(name))


# ---------------------------------------------------------------------------
# Синонимы
# ---------------------------------------------------------------------------

def load_alias_groups() -> list:
    groups = [list(g) for g in DEFAULT_ALIAS_GROUPS]
    if ALIASES_FILE.exists():
        try:
            extra = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
            groups.extend(list(g) for g in extra if isinstance(g, list))
        except Exception:
            pass
    return groups


def _phrases_for(team: str, alias_groups: list) -> list:
    sk = _skeleton(team)
    for group in alias_groups:
        if any(_skeleton(p) == sk for p in group):
            result = [team] + [p for p in group if _skeleton(p) != sk]
            return result
    return [team]


# ---------------------------------------------------------------------------
# Поиск команды в токенах заголовка
# ---------------------------------------------------------------------------

def _is_name_like(tok) -> bool:
    return (tok is not None and tok != SEP and tok.isalpha()
            and len(tok) >= 2 and tok not in NOISE_TOKENS)


def _span_ok(tokens, start, end, target_tokens) -> bool:
    nxt = tokens[end] if end < len(tokens) else None
    prv = tokens[start - 1] if start > 0 else None
    if nxt is not None:
        # "юниор 2" не должен совпасть с командой "юниор" (другой состав)
        if nxt.isdigit() and len(nxt) == 1 and not target_tokens[-1].isdigit():
            return False
        # "ска" не должна совпасть внутри "ска хкд"
        if _is_name_like(nxt):
            return False
    if _is_name_like(prv):
        return False
    return True


def _find_spans(tokens, target_tokens):
    """Все места, где команда встречается в заголовке. Токены склеиваются,
    поэтому "гуд"+"гол" совпадает с "гудгол"."""
    target = "".join(target_tokens)
    if not target:
        return []
    spans = []
    n = len(tokens)
    for i in range(n):
        if tokens[i] == SEP:
            continue
        acc = ""
        for j in range(i, n):
            if tokens[j] == SEP:
                break
            acc += tokens[j]
            if not target.startswith(acc):
                break
            if acc == target:
                if _span_ok(tokens, i, j + 1, target_tokens):
                    spans.append((i, j + 1))
                break
    return spans


def _team_spans(tokens, team, alias_groups, allow_squad_omit=False):
    phrases = _phrases_for(team, alias_groups)
    if allow_squad_omit:
        # "Красная Машина Юниор 2" может быть записана в заголовке без номера
        # состава — проверяем и вариант без цифры (только во втором проходе).
        toks = tokenize_name(team)
        if len(toks) > 1 and toks[-1].isdigit() and len(toks[-1]) == 1:
            phrases = phrases + _phrases_for(" ".join(toks[:-1]), alias_groups)
    spans = []
    for phrase in phrases:
        spans.extend(_find_spans(tokens, tokenize_name(phrase)))
    return spans


def mentions_team(tokens, team, alias_groups) -> int:
    """Мягкая проверка: упомянута ли команда в заголовке в любой форме —
    без учёта номера состава и без защит от "обрыва" названия. Для
    ревизии и фильтра очереди, НЕ для автоматической привязки.
    Возвращает длину совпадения в токенах (0 — не упомянута)."""
    words = [t for t in tokens if t != SEP]
    best = 0
    for phrase in _phrases_for(team, alias_groups):
        tt = tokenize_name(phrase)
        # Номер состава отбрасываем, только если без него остаётся
        # полноценное название ("ска звезда 2" -> "ска звезда"), а не
        # аббревиатура, где цифра — часть имени ("сш 1" остаётся "сш 1").
        if len(tt) > 1 and tt[-1].isdigit() and len(tt[-1]) == 1 and len("".join(tt[:-1])) >= 4:
            tt = tt[:-1]
        target = "".join(tt)
        if not target:
            continue
        for i in range(len(words)):
            acc = ""
            for j in range(i, len(words)):
                acc += words[j]
                if not target.startswith(acc):
                    break
                if acc == target:
                    best = max(best, j - i + 1)
                    break
    return best


def _best_pair(spans1, spans2):
    best = None
    for a in spans1:
        for b in spans2:
            if a[1] <= b[0] or b[1] <= a[0]:
                size = (a[1] - a[0]) + (b[1] - b[0])
                if best is None or size > best:
                    best = size
    return best


# ---------------------------------------------------------------------------
# Расписание
# ---------------------------------------------------------------------------

def _parse_key(key: str):
    parts = key.split("::")
    if len(parts) < 2 or "|" not in parts[1]:
        return None
    date = parts[0]
    team1, team2 = parts[1].split("|", 1)
    age = parts[2] if len(parts) > 2 and parts[2] else None
    return {"date": date, "team1": team1, "team2": team2, "age": age, "key": key}


def load_fixtures() -> dict:
    """{дата: [матчи]}. Если есть official_fixtures.json (с возрастами) —
    берём его, иначе восстанавливаем из ключей official_matches.json."""
    fixtures = {}
    if FIXTURES_FILE.exists():
        try:
            data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
            for fx in data:
                fixtures.setdefault(fx["date"], []).append(fx)
            return fixtures
        except Exception:
            fixtures = {}
    if OFFICIAL_KEYS_FILE.exists():
        keys = json.loads(OFFICIAL_KEYS_FILE.read_text(encoding="utf-8"))
        for key in keys:
            fx = _parse_key(key)
            if fx:
                fixtures.setdefault(fx["date"], []).append(fx)
    return fixtures


# ---------------------------------------------------------------------------
# Даты-кандидаты
# ---------------------------------------------------------------------------

_TITLE_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b")


def extract_title_date(title: str, ref_year: int):
    m = _TITLE_DATE_RE.search(title or "")
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    if year is None:
        y = ref_year
    elif len(year) == 2:
        y = 2000 + int(year)
    else:
        y = int(year)
    try:
        return datetime(y, month, day).strftime("%d.%m.%Y")
    except ValueError:
        return None


ANNOUNCE_AHEAD_DAYS = 7      # анонс без даты: матч может быть до недели после загрузки


def build_date_candidates(title: str, live_start_ts=None, upload_ts=None, window: int = 3) -> list:
    """Если дата есть в заголовке — только она. Иначе — дата начала
    трансляции (или загрузки) и соседние дни: +1, -1, +2, -2 ..."""
    base_ts = live_start_ts or upload_ts
    ref_year = datetime.fromtimestamp(base_ts).year if base_ts else datetime.now().year
    td = extract_title_date(title, ref_year)
    if td and base_ts:
        # Опечатка в заголовке ("04.10.25" вместо "04.10.26"): если дата
        # из заголовка дальше месяца от трансляции — верим трансляции.
        gap = abs((datetime.strptime(td, "%d.%m.%Y") - datetime.fromtimestamp(base_ts)).days)
        if gap > 31:
            td = None
    if td:
        return [td]
    if not base_ts:
        return []
    base = datetime.fromtimestamp(base_ts)
    days = [0]
    for k in range(1, window + 1):
        days += [k, -k]
    if not live_start_ts:
        # Только дата загрузки (анонс без даты и без времени начала):
        # клубы выкладывают анонсы за несколько дней — смотрим неделю вперёд.
        days += list(range(window + 1, ANNOUNCE_AHEAD_DAYS + 1))
    return [(base + timedelta(days=d)).strftime("%d.%m.%Y") for d in days]


_TITLE_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


def _hm(text):
    """'9:00' / '09:00' -> (9, 0); None, если времени нет."""
    m = re.match(r"\s*(\d{1,2}):(\d{2})", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _minutes_from(fx: dict, start_dt) -> float:
    """Сколько минут между временем матча в расписании и началом
    трансляции. Если время матча неизвестно — бесконечность."""
    t = fx.get("time")
    if not t or ":" not in t:
        return float("inf")
    try:
        h, m = map(int, t.split(":")[:2])
        match_dt = datetime.strptime(fx["date"], "%d.%m.%Y").replace(hour=h, minute=m)
    except ValueError:
        return float("inf")
    return abs((match_dt - start_dt).total_seconds()) / 60


# ---------------------------------------------------------------------------
# Главная функция
# ---------------------------------------------------------------------------

def match_title(title: str, date_candidates: list, fixtures: dict = None,
                alias_groups: list = None, start_dt=None):
    """Сопоставление; если не нашлось — повтор с исправленными опечатками в названиях команд."""
    fx, why = _match_title_exact(title, date_candidates, fixtures, alias_groups, start_dt)
    if fx is not None:
        return fx, why
    fixed, changes = _fix_typos(title, date_candidates, fixtures, alias_groups)
    if not changes:
        return fx, why
    fx2, why2 = _match_title_exact(fixed, date_candidates, fixtures, alias_groups, start_dt)
    if fx2 is None:
        return fx, why
    return fx2, f"{why2} (исправлена опечатка: {', '.join(changes)})"


def _fix_typos(title, date_candidates, fixtures, alias_groups, min_ratio=0.84):
    """Заменяет в заголовке слова-опечатки (от 6 букв) на похожие слова из названий команд этих дней."""
    import difflib
    if fixtures is None:
        fixtures = load_fixtures()
    vocab = set()
    for d in date_candidates or []:
        for f in fixtures.get(d, []):
            for team in (f.get("team1", ""), f.get("team2", "")):
                vocab.update(w for w in re.findall(r"[а-яё]+", team.lower()) if len(w) >= 5)
    for group in alias_groups or []:
        for name in group:
            vocab.update(w for w in re.findall(r"[а-яё]+", name.lower()) if len(w) >= 5)
    if not vocab:
        return title, []
    changes = []

    def repl(m):
        word = m.group(0)
        low = word.lower().replace("ё", "е")
        if len(low) < 6 or low in vocab:
            return word
        best, score = None, 0.0
        for v in vocab:
            if v[0] != low[0] or abs(len(v) - len(low)) > 2:
                continue
            r = difflib.SequenceMatcher(None, low, v).ratio()
            if r > score:
                best, score = v, r
        if best and score >= min_ratio:
            changes.append(f"{word}→{best}")
            return best.upper() if word.isupper() else best
        return word
    fixed = re.sub(r"[А-Яа-яЁё]+", repl, title)
    return fixed, changes


def _match_title_exact(title: str, date_candidates: list, fixtures: dict = None,
                       alias_groups: list = None, start_dt=None):
    """
    Возвращает (матч | None, причина).
    матч = {"date", "team1", "team2", "age", "key"} — ровно как в
    официальном расписании, поэтому ключ совпадает с тем, что ищет
    post_schedule.py.
    """
    low = (title or "").lower()
    if any(w in low for w in REVIEW_WORDS):
        return None, "обзор/нарезка — не сопоставляем"
    if not date_candidates:
        return None, "нет даты"

    fixtures = fixtures if fixtures is not None else load_fixtures()
    alias_groups = alias_groups if alias_groups is not None else load_alias_groups()

    tokens, ages = tokenize_title(title)
    distinct_ages = set(ages)
    title_age = distinct_ages.pop() if len(distinct_ages) == 1 else None

    title_time = _hm(_TITLE_TIME_RE.search(title or "").group(0)) if _TITLE_TIME_RE.search(title or "") else None

    def collect(allow_squad_omit):
        found = []
        for idx, date in enumerate(date_candidates):
            for fx in fixtures.get(date, []):
                fx_age = fx.get("age")
                if title_age and fx_age and fx_age != title_age:
                    continue
                s1 = _team_spans(tokens, fx["team1"], alias_groups, allow_squad_omit)
                if not s1:
                    continue
                s2 = _team_spans(tokens, fx["team2"], alias_groups, allow_squad_omit)
                if not s2:
                    continue
                size = _best_pair(s1, s2)
                if size is None:
                    continue
                score = size + (5 if (title_age and fx_age == title_age) else 0) - 0.01 * idx
                if title_time and _hm(fx.get("time")) == title_time:
                    score += 0.5      # время из заголовка совпало с временем матча
                found.append((score, fx))
        return found

    scored = collect(False)
    if not scored:
        # Второй проход: соперник мог быть записан без номера состава.
        # Принимается, только если вариант единственный (см. проверку ниже).
        scored = collect(True)

    if not scored:
        return None, "ни один официальный матч не подошёл"

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_fx = scored[0]
    # Соперник — любой ДРУГОЙ матч (в т.ч. та же пара клубов в другом
    # возрасте: ключ у них одинаковый, различаются только возрастом).
    best_id = (best_fx["key"], best_fx.get("age"))
    rivals = [fx for s, fx in scored[1:]
              if abs(s - best_score) < 1e-9 and (fx["key"], fx.get("age")) != best_id]
    if rivals and start_dt is not None:
        # Неоднозначно (например, та же пара клубов в двух возрастах в один
        # день) — пробуем решить по времени начала трансляции: подходит
        # матч, который начинается в пределах часа от неё, и он один.
        near = [fx for fx in [best_fx] + rivals if _minutes_from(fx, start_dt) <= 60]
        if len(near) == 1:
            best_fx, rivals = near[0], []
    if rivals:
        names = ", ".join(f'{fx["team1"]} — {fx["team2"]} ({fx.get("age") or "?"})' for fx in [best_fx] + rivals)
        return None, f"неоднозначно: {names}"

    result = dict(best_fx)
    if not result.get("age") and title_age:
        result["age"] = title_age
    return result, "ok"
