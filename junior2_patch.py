#!/usr/bin/env python3
"""
1. generate_banner_v3.py: «Территория хоккея» — плашка как у Кубка России
   (синяя с триколором); свой логотип турнира без круга
   (python3 generate_banner_v3.py --fetch-territoriya-logo [НОМЕР]).
2. post_schedule.py: протокол матча (вратари, штрафы, передачи) берётся с сайта
   самой игры — для Кубка России и «Территории хоккея» с junior.fhr.ru, а не
   с spb.fhr.ru. Теперь у них на баннере та же сводка, что у Кубка СПб.

Запуск (из ~/vk-bot):  python3 junior2_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

GEN = [
    ('''             TERRITORIYA_TEAL if tournament.startswith("ТЕРРИТОРИЯ") else CUP_AMBER)''',
     '''             ROSSII_BLUE if tournament.startswith("ТЕРРИТОРИЯ") else CUP_AMBER)'''),
    ('''    if tournament == "КУБОК РОССИИ":                  # триколор под плашкой''',
     '''    if tournament == "КУБОК РОССИИ" or tournament.startswith("ТЕРРИТОРИЯ"):   # триколор под плашкой'''),
    ('''    if tournament == "КУБОК РОССИИ" and KR_LOGO_PATH.exists():
        # Логотип Кубка России — без круга, крупнее, без собственного фона
        logo = _logo_without_background(Image.open(KR_LOGO_PATH))''',
     '''    own_logo = (KR_LOGO_PATH if tournament == "КУБОК РОССИИ" else
                TERR_LOGO_PATH if tournament.startswith("ТЕРРИТОРИЯ") else None)
    if own_logo is not None and own_logo.exists():
        # Свой логотип турнира — без круга, крупнее, без собственного фона
        logo = _logo_without_background(Image.open(own_logo))'''),
    ('''KR_LOGO_PATH = BASE / "kubok_rossii_logo.png"''',
     '''TERR_LOGO_PATH = BASE / "territoriya_logo.png" # логотип «Территории хоккея» (--fetch-territoriya-logo)
KR_LOGO_PATH = BASE / "kubok_rossii_logo.png"'''),
    ('''def fetch_kr_logo(pick=None):''', '''def fetch_kr_logo(pick=None, slug=None, out=None, flag="--fetch-kr-logo"):'''),
    ('''    page = s.get(f"{base}/tournaments/{c.KUBOK_ROSSII_TOURNAMENT_SLUG}/", timeout=25).text''',
     '''    slug = slug or c.KUBOK_ROSSII_TOURNAMENT_SLUG
    out = out or KR_LOGO_PATH
    page = s.get(f"{base}/tournaments/{slug}/", timeout=25).text'''),
    ('''    Image.open(io.BytesIO(data)).convert("RGBA").save(KR_LOGO_PATH)
    print(f"Сохранён [{pick}] как {KR_LOGO_PATH.name} — откройте и проверьте: open {KR_LOGO_PATH.name}")
    print("Если это не тот логотип, выберите другой номер: python3 generate_banner_v3.py --fetch-kr-logo НОМЕР")''',
     '''    Image.open(io.BytesIO(data)).convert("RGBA").save(out)
    print(f"Сохранён [{pick}] как {out.name} — откройте и проверьте: open {out.name}")
    print(f"Если это не тот логотип, выберите другой номер: python3 generate_banner_v3.py {flag} НОМЕР")'''),
    ('''    if "--fetch-kr-logo" in sys.argv:''',
     '''    if "--fetch-territoriya-logo" in sys.argv:
        i = sys.argv.index("--fetch-territoriya-logo")
        n = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else None
        fetch_kr_logo(n, "territoriya-khokkeya-u15-26308586", TERR_LOGO_PATH, "--fetch-territoriya-logo")
        return
    if "--fetch-kr-logo" in sys.argv:'''),
]

PS = [
    ('''def _protocol_summary(game_id, expected_goals):''', '''def _protocol_summary(game_id, expected_goals, url=None):'''),
    ('''        if _protocol_session is None:
            _protocol_session = spb_fhr_client.create_session()
        page = _protocol_session.get(f"https://spb.fhr.ru/games/{game_id}/", timeout=25).text''',
     '''        target = url or f"https://spb.fhr.ru/games/{game_id}/"      # протокол — с сайта самой игры
        if spb_fhr_client.KUBOK_ROSSII_DOMAIN in target:
            session = _PROTOCOL_SESSIONS.get("junior") or _PROTOCOL_SESSIONS.setdefault(
                "junior", spb_fhr_client.create_session_kubok_rossii())
        else:
            if _protocol_session is None:
                _protocol_session = spb_fhr_client.create_session()
            session = _protocol_session
        page = session.get(target, timeout=25).text'''),
    ('''_protocol_session = None
''', '''_protocol_session = None
_PROTOCOL_SESSIONS = {}
'''),
    ('''    summary = _protocol_summary(sm["game_id"], sc[0] + sc[1])''',
     '''    summary = _protocol_summary(sm["game_id"], sc[0] + sc[1], sm.get("game_url"))'''),
]


def patch(path, items, marker):
    c = path.read_text(encoding="utf-8")
    if marker in c:
        print(f"{path.name}: уже исправлено")
        return False
    missing = [o[:50] for o, _ in items if c.count(o) != 1]
    if missing:
        print(f"{path.name}: НЕ найдено {missing} — файл НЕ изменён")
        return False
    shutil.copy(path, path.with_name(path.name + ".bak_junior2"))
    for o, n in items:
        c = c.replace(o, n, 1)
    path.write_text(c, encoding="utf-8")
    return True


def main():
    if patch(BASE / "generate_banner_v3.py", GEN, "TERR_LOGO_PATH"):
        print("generate_banner_v3.py: «Территория хоккея» — плашка как у Кубка России, свой логотип")
    if patch(BASE / "post_schedule.py", PS, "_PROTOCOL_SESSIONS"):
        print("post_schedule.py: протокол матча — с сайта самой игры (junior.fhr.ru для Кубка России и «Территории»)")


if __name__ == "__main__":
    main()
