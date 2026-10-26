#!/usr/bin/env python3
"""
post_schedule.py: если голы по периодам на spb.fhr.ru не сходятся со счётом,
бот больше не скачивает страницу матча на КАЖДОМ прогоне. Перепроверка
затухает: 6 раз — раз в 10 минут, затем раз в час, после 30 попыток (~сутки)
бот перестаёт дёргать сайт и показывает то, что есть. Из-за бесконечных
повторов по сотне матчей прогон шёл дольше 2 минут и каждый второй пропускался.

Запуск (из ~/vk-bot):  python3 details_retry_patch.py
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_schedule.py"

OLD = '''                elif spb_session is not None:
                    try:
                        details = spb_fhr_client.fetch_match_live_details(spb_session, spb_match["game_id"], domain=domain)
                        periods_breakdown = details["periods_breakdown"]
                        # Сохраняем ВСЕГДА'''
NEW = '''                elif spb_session is not None and _details_retry_due(spb_match["game_id"]):
                    _details_retry_mark(spb_match["game_id"])
                    try:
                        details = spb_fhr_client.fetch_match_live_details(spb_session, spb_match["game_id"], domain=domain)
                        periods_breakdown = details["periods_breakdown"]
                        # Сохраняем ВСЕГДА'''

ANCHOR = "def format_caption("
HELPERS = '''# ---------- неполные данные завершённого матча: перепроверка с затуханием ----------
_DETAILS_RETRY_FILE = Path(__file__).parent / "spb_details_retry.json"
_DETAILS_RETRY = None


def _details_retry_state():
    global _DETAILS_RETRY
    if _DETAILS_RETRY is None:
        try:
            _DETAILS_RETRY = json.loads(_DETAILS_RETRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            _DETAILS_RETRY = {}
    return _DETAILS_RETRY


def _details_retry_due(game_id):
    """Пора ли снова скачать страницу матча: 6 раз — раз в 10 мин, потом раз в час, после 30 — нет."""
    last, tries = _details_retry_state().get(str(game_id), [0, 0])
    if tries >= 30:
        return False
    return time.time() - last >= (600 if tries < 6 else 3600)


def _details_retry_mark(game_id):
    state = _details_retry_state()
    last, tries = state.get(str(game_id), [0, 0])
    state[str(game_id)] = [time.time(), tries + 1]
    try:
        _DETAILS_RETRY_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


'''

TEST_ADD = '''

def test_details_retry():
    """Неполные данные матча перепроверяются с затуханием, а не на каждом прогоне."""
    with quiet():
        import post_schedule as ps
    import time as _t
    ps._DETAILS_RETRY = {}
    ps._DETAILS_RETRY_FILE = HERE / "retry_test.json"
    assert ps._details_retry_due("1")
    ps._details_retry_mark("1")
    assert not ps._details_retry_due("1")                     # сразу повторно — нет
    ps._DETAILS_RETRY["1"][0] -= 601
    assert ps._details_retry_due("1")                         # через 10 минут — да
    ps._DETAILS_RETRY["1"] = [_t.time() - 4000, 30]
    assert not ps._details_retry_due("1")                     # после 30 попыток — больше не дёргаем
'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "_details_retry_due" in content:
        print("post_schedule.py: уже исправлено")
    else:
        if content.count(OLD) != 1 or content.count(ANCHOR) != 1:
            sys.exit("post_schedule.py: место не найдено — файл НЕ изменён")
        shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_retry"))
        content = content.replace(OLD, NEW).replace(ANCHOR, HELPERS + ANCHOR, 1)
        TARGET.write_text(content, encoding="utf-8")
        print("post_schedule.py: неполные данные матча перепроверяются с затуханием")
    cases = TARGET.parent / "tests" / "cases.py"
    if cases.exists() and "test_details_retry" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест затухающей перепроверки")


if __name__ == "__main__":
    main()
