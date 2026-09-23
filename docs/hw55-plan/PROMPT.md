# Prompt startowy — praca domowa 5.5, faza po fazie

Wklej poniższe do nowej sesji Claude Code w katalogu `trading-desk` na komputerze domowym.
Do kolejnych faz wystarczy: „Faza N — zaczynamy”.

---

Pracujemy razem nad pracą domową 5.5 z kursu Python: migracja backendu z WSGI (Bottle) na
ASGI (FastAPI) — benchmark, decyzja go/no-go, analiza ryzyk, refactor albo plan alternatywny.
PDF z zadaniem: <ŚCIEŻKA DO PDF>. Repozytorium: `trading-desk`, zasady w `AGENTS.md`.

**Plan:** `docs/hw55-plan/PLAN.md` z gałęzi `claude/plan-requirements-review-78tlz6`
(`git show origin/claude/plan-requirements-review-78tlz6:docs/hw55-plan/PLAN.md`). Przeczytaj
go całego przed pierwszym krokiem. Ta sama gałąź zawiera pilot (kod `benchmark/`, wyniki,
raport) — to materiał referencyjny i lista znanych pułapek, **nie** kod do skopiowania.
Zaczynamy od zera: nowa gałąź `hw-5.5-asgi-migration` od commita `bc7f5e2`.

**Jak pracujemy:**

1. Jedna faza na raz, w kolejności z planu. Na początku fazy pokaż mi jej kroki i
   **prognozę** (co powinno wyjść i z jakiej arytmetyki). Na końcu fazy zatrzymaj się:
   streszczenie, commit(y), plik prywatny i pytania do rozmowy. Nie zaczynaj następnej fazy
   bez mojego „dalej”.
2. **Minimum kodu.** Trzymaj budżet linii z planu. Zanim dodasz plik, scenariusz, wariant albo
   parametr, powiedz, na jakie pytanie z PDF odpowiada. Jeśli na żadne — nie dodawaj.
   Żadnego strojenia pul, uvloop „na zapas”, dodatkowych N.
3. **Kryteria przed pomiarem**, osobny commit. Prognozy zapisane przed runem.
4. **Pomiary w Dockerze** (`benchmark/compose.yml`, `cpuset` dla serwerów). Zanim poprosisz
   mnie o puszczenie długiego runu, zrób test dymny (3 s na punkt) i przejdź listę kontrolną
   z planu. Długie runy puszczam ja; podaj dokładną komendę i szacowany czas.
5. **Trzy ślady każdej fazy:**
   - sekcja `docs/report.md` (po angielsku, rzeczowo, jak w PR 4);
   - commit z opisem, co i po co (krótkie, rzeczowe wiadomości, trailer Co-Authored-By);
   - **prywatny plik tury** `tmp/hw55/NN-faza-temat.md` po polsku, wg szablonu z planu:
     co zrobiliśmy, decyzje i odrzucone alternatywy, technologia wyjaśniona od zera, liczby
     do zapamiętania, pułapki, reguły na przyszłe testy, pytania do rozmowy. Pisz tak,
     żebym za pół roku zrozumiał bez tej rozmowy. Dopisuj pojęcia do `tmp/hw55/00-slownik.md`.
6. **Ucz, nie tylko rób.** Przy każdej decyzji technicznej (gunicorn sync vs gthread, pętla
   zdarzeń, GIL, kolejka nasłuchu, keep-alive, percentyle, klient zamknięty vs otwarty)
   wyjaśnij mechanizm w 2–4 zdaniach i pokaż, jak widać go w liczbach. Gdy wynik nie zgadza
   się z prognozą — zatrzymaj się i wyjaśnij, zanim pójdziemy dalej.
7. **Uczciwość:** raportuj błędy obok latencji, rozrzut obok mediany, i to, czego nie
   sprawdziliśmy. Nie dopasowuj kryteriów do wyniku.

Zacznij od fazy 0: przeczytaj PLAN.md, PDF, `docs/report.md` z PR 4 i kod
`libs/desk-runtime`, potem pokaż mi kroki fazy 0 z prognozą i poczekaj na „dalej”.
