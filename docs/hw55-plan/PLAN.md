# Praca domowa 5.5 — plan wykonania od zera, faza po fazie

Plan do wspólnego przejścia (Jakub + Claude) na komputerze domowym, z pomiarami w Dockerze.
Każda faza odpowiada etapowi z PDF. Każda kończy się **zatrzymaniem na rozmowę**, zanim
ruszy następna.

Ten plan korzysta z wniosków pilota z 22–23.09 (gałąź `claude/plan-requirements-review-78tlz6`).
Pilot nie jest wynikiem oddawanej pracy, tylko mapą min: wiemy, gdzie pomiar potrafi
kłamać, i od początku projektujemy tak, żeby nie kłamał.

---

## Zasady na całą pracę

1. **Pytanie jest jedno:** czy przejście z WSGI na ASGI coś daje *temu* systemowi. Wszystko,
   co nie pomaga na nie odpowiedzieć, wypada (strojenie pul, uvloop „na wszelki wypadek”,
   dodatkowe N, kolejne scenariusze).
2. **Najpierw prognoza, potem pomiar.** Przed każdym pomiarem zapisujemy, co ma wyjść, i
   dlaczego (prosta arytmetyka). Pomiar ma potwierdzić model albo go obalić. Tak się uczy
   najwięcej i tak się broni wynik.
3. **Minimum kodu.** Każda faza ma budżet linii. Jeśli rośnie, pytamy, czy nie odpowiadamy na
   inne pytanie niż PDF.
4. **Kryteria przed pomiarem**, osobny commit (wymóg PDF).
5. **Docker na pomiar.** Jeden obraz, warianty to różne komendy; rdzenie przydzielone przez
   `cpuset`, żeby generator i serwer nie walczyły o CPU. Na macOS nie ma `taskset`, a
   Docker to załatwia przenośnie. Prowadzący odtworzy wszystko jednym poleceniem.
6. **Każda faza zostawia trzy ślady:**
   - publiczny: sekcja `docs/report.md` (+ `docs/decision_criteria.md` w fazie 0);
   - kod/wyniki: commit z opisem, co i po co;
   - prywatny: plik tury w `tmp/hw55/` (gitignored), patrz niżej.

### Pliki prywatne (na naukę, nie do oddania)

`tmp/hw55/NN-faza-temat.md`, jeden na turę pracy. Szablon:

```
# NN — <temat>
## Co zrobiliśmy (3–6 zdań)
## Decyzje i odrzucone alternatywy (dlaczego tak, a nie inaczej)
## Technologia wyjaśniona od zera (np. jak gunicorn gthread przyjmuje połączenie)
## Liczby, które warto pamiętać (i skąd się biorą)
## Pułapki, na które wpadliśmy albo prawie
## Czego się nauczyć na przyszłe testy (reguły ogólne, nie tylko ten projekt)
## Pytania do rozmowy (3–5, takie jak na rozmowie rekrutacyjnej)
```

Obok stały słownik `tmp/hw55/00-slownik.md` (Little's law, p95, closed/open loop, GIL,
event loop, backlog, TCP_NODELAY, keep-alive, coordinated omission…), dopisywany na bieżąco.

---

## Faza 0 — Inwentaryzacja i założenia  (PDF: etap 0 + kryteria z etapu 2 · ~10 %)

**Po co:** bez wiedzy, jaki ruch system naprawdę ma i na co naprawdę czeka, benchmark mierzy
wymyślony problem. Ta faza zamienia szacunki z PR 4 na **zmierzone liczby**.

### Kroki

1. **Gałąź od zera.** `hw-5.5-asgi-migration` od `bc7f5e2`. Inwentaryzacja z PR 4 zostaje,
   poprawiamy tylko to, co pilot pokazał jako błędne (serwer to wsgiref + ThreadingMixIn,
   HTTP/1.0, kolejka nasłuchu 5 — nie „built-in Bottle server”).
2. **Zmierz realny ruch zamiast go szacować.** *Urealnienie #1.* Otwórz UI na 5 minut
   (zwykła praca: market data, blotter, logi), zapisz w DevTools zakładkę Network jako HAR.
   Skrypt `benchmark/har_concurrency.py` (~25 linii) liczy per serwis: żądania/s, maksymalną
   liczbę żądań w locie, liczbę otwartych strumieni SSE.
   *Po co:* bramka 4 („czy system tego potrzebuje”) opiera się wtedy na pomiarze, nie na
   „około pięciu”.
3. **Zmierz, na co serwisy czekają.** *Urealnienie #2.* Czas prawdziwego wywołania
   serwis→serwis (`curl -w '%{time_total}'` na `pricing → market-data /snapshot`, 50 prób)
   i, jeśli dostępne, czasy zapytań do dostawców z `provider_request_ledger`.
   Wynik: mediana i p95 opóźnienia → **parametry stubu** w S2 (zamiast sztywnych 50 ms).
4. **Charakter obciążenia z dowodem.** `py-spy top` na jednym serwisie przy ruchu z UI:
   czy czas idzie w czekanie (socket/DB), czy w CPU. Jedno zdanie + zrzut do raportu.
5. **Wybór próbki:** books-service (jedyny bez wątków w tle i stanu w pamięci) + stub
   udający inny serwis. Uzasadnienie już jest w PR 4.
6. **Kryteria i prognozy** → `docs/decision_criteria.md`, **osobny commit**:
   - warianty: A (gunicorn sync), A′ (gunicorn gthread, 40 wątków), B (FastAPI na uvicorn),
     A0 (dzisiejszy serwer wsgiref — *as-is*, dopiero w fazie 4, ale nazwany już tu);
   - reguła niepewności (różnica > rozrzut), reguła błędów (> 1 % = przegrany punkt);
   - 4 bramki (jak w pilocie; bramka 1 na S4, nie na pustym `/health` — to lekcja z pilota);
   - **prognozy liczbowe** dla każdego wariantu w S2 (np. A = 1/opóźnienie,
     A′ = min(c, 40)/opóźnienie, B = c/opóźnienie aż do sufitu CPU).

**Budżet kodu:** ~25 linii (`har_concurrency.py`). **Commity:** inwentaryzacja; kryteria.
**Prywatne pliki:** `01-inwentaryzacja-ruch.md`, `02-kryteria-i-prognozy.md`.

**Do rozmowy po fazie:** co to jest „c” w benchmarku, a co to jest ruch z przeglądarki?
Dlaczego kryteria przed pomiarem? Jak z prawa Little'a wyliczyć liczbę żądań w locie?

---

## Faza 1 — Benchmark na próbce  (PDF: etap 1 · ~30 %)

**Po co:** zmierzyć różnicę WSGI–ASGI dokładnie tam, gdzie ma prawo wystąpić (czekanie), i
sprawdzić kontrolnie, że nie ma jej tam, gdzie nie powinno być (CPU, prosty CRUD).

### Kroki

1. **Próbka w dwóch wersjach** (`benchmark/sample_wsgi`, `sample_asgi`, ~70 linii razem):
   S1 `/health`, S2 `/io`, S3 `/cpu`, S4 `/books` — w Bottle prawdziwa aplikacja books
   dołączona `app.merge`, w FastAPI to samo wywołanie repozytorium. `async def` tylko przy
   nieblokującym I/O (S1, S2); S3 i S4 jako `def` — pułapka nr 1 z PDF.
2. **Stub z realistycznym opóźnieniem** (`benchmark/stub`, ~15 linii). *Urealnienie #3.*
   Zamiast stałych 50 ms: losowanie z rozkładu log-normalnego dopasowanego do mediany i p95
   z fazy 0. *Po co:* prawdziwe usługi mają ogony; ogon zależności przenosi się na ogon
   serwisu i to go widać w p99. Stała wartość tego nie pokaże.
3. **Jeden plik compose** `benchmark/compose.yml` (~50 linii): `postgres` (z głównego
   compose), `stub`, `a`, `a-threads`, `b`, `loadgen` (obraz z `hey`). Każdy serwer
   `cpuset: "0"`, reszta na pozostałych rdzeniach. *Po co:* PDF wymaga, żeby klient i
   serwer nie konkurowały o rdzenie; w Dockerze to dwie linie na serwis.
4. **Skrypt siatki** `benchmark/run.sh` (~40 linii): 4 scenariusze × c = 1/10/50/200 ×
   warianty × 3 powtórzenia; warianty przeplatane w każdym punkcie; 10 s rozgrzewki,
   30 s pomiaru, `hey -t 10`; `docker stats --no-stream` co sekundę do pliku (CPU, pamięć).
5. **Test dymny (3 s na punkt, ~4 min) i lista kontrolna** — zanim ruszy 2-godzinny run:
   - liczba workerów w logach się zgadza;
   - stub sam przy c = 200 trzyma zadany rozkład (inaczej mierzymy stub);
   - `/health` przy c = 1 ma < 1 ms (inaczej coś jest nie tak z TCP, pilot: `TCP_NODELAY`);
   - A w S2 daje ~1/opóźnienie req/s (arytmetyka się zgadza);
   - błędy są tam, gdzie mają być.
6. **Pełny run** (~2 h, w nocy). **Analiza** `benchmark/analyze.py` (~150 linii):
   mediana + min–max, tabele, 2 wykresy na scenariusz, automatyczne sprawdzenie bramek.
7. **Opcjonalnie, jedna kontrola wrażliwości:** S2 dodatkowo przy stałym tempie
   (`hey -q`, ruch otwarty) na poziomie 10× dzisiejszego szczytu. *Urealnienie #4.*
   *Po co:* `hey -c` to klient zamknięty — gdy serwer zwalnia, klient też zwalnia i ukrywa
   kolejkę (*coordinated omission*). Stałe tempo pokazuje, co poczułby użytkownik.

**Budżet kodu:** ~330 linii razem z analizą. **Commity:** próbka i skrypty; wyniki + sekcje
3–5 raportu. **Prywatne pliki:** `03-uczciwy-benchmark.md` (zasady z PDF 5.1 i dlaczego
każda istnieje), `04-docker-cpuset-i-siec.md`, `05-test-dymny.md`, `06-wyniki-i-arytmetyka.md`.

**Do rozmowy:** dlaczego średnia kłamie, a p95 też potrafi (błędy poza percentylami)? Czemu
wątki remisują z async do 40 klientów? Co to jest koszt CPU na żądanie i jak go policzyć z
`CPU% / req/s`? Czym różni się klient zamknięty od otwartego?

---

## Faza 2 — Decyzja go/no-go  (PDF: etap 2 · ~10 %)

**Po co:** zamienić liczby w decyzję, którą da się obronić, wg szablonu ADR z PDF 5.3.

### Kroki

1. Bramki 1, 2, 4 z `analyze.py` — bez interpretacji „na oko”.
2. **Bramka 3 — koszt z pilota, nie z sufitu.** Przepisanie `GET /books` na FastAPI w fazie 1
   *jest* małym pilotem: zapisujemy jego realny czas i ekstrapolujemy na 50 endpointów +
   strumienie SSE + wątki w tle + testy kontraktowe. Tabela per serwis.
3. ADR: kontekst, kryteria (link do commita), dane z niepewnością, 3 opcje (pełna migracja /
   zostajemy + poprawki / częściowa), decyzja, konsekwencje, warunki rewizji.

**Budżet kodu:** 0. **Commit:** sekcja 6 raportu. **Prywatny plik:** `07-adr-jak-decydowac.md`.

**Do rozmowy:** co przesądziło i co musiałoby się zmienić, żeby decyzja się odwróciła?
Czym różni się „nie opłaca się” od „nie chce mi się” (PDF tego pilnuje)?

---

## Faza 3 — Analiza zagrożeń  (PDF: etap 3 · ~10 %)

**Po co:** zobaczyć, co by się zepsuło przy migracji, zanim się zepsuje.

1. Macierz ≥ 8 ryzyk (P, W, ograniczenie, **sygnał ostrzegawczy jako metryka**). Starter z
   PDF 5.4 rozszerzony o ryzyka tego systemu: 54 synchroniczne sesje DB, strumienie SSE na
   `queue.Queue`, stan w pamięci, format `{"error"}` czytany przez frontend, brak testów.
2. Dwa ryzyka z pomiaru, nie z teorii (pilot: `TCP_NODELAY` w wielu workerach uvicorna,
   koszt CPU klienta httpx).

**Budżet kodu:** 0. **Commit:** sekcja 7. **Prywatny plik:** `08-ryzyka.md`.

---

## Faza 4B (NO-GO) — plan alternatywny i jedna realna poprawa  (PDF: etap 4 · ~40 %)

*(Jeśli wyjdzie GO, w tym miejscu robimy 4A wg checklisty PDF 5.5: testy kontraktowe →
books-service jako pilot → serwis po serwisie. Plan 4A rozpisujemy dopiero po decyzji.)*

**Po co:** NO-GO nie może znaczyć „nic nie robię”. Wdrażamy najtańszą rzecz, która według
pomiaru daje najwięcej, i mierzymy ją przed/po.

### Kroki

1. **Plan alternatywny** — tabela: pozycja, koszt, spodziewany efekt, status. Kandydaci:
   (a) gunicorn gthread zamiast wsgiref w `desk-runtime`, (b) testy kontraktowe,
   (c) pula DB dopasowana do liczby wątków, (d) async tylko dla market-data przy spełnieniu
   warunku rewizji.
2. **Najpierw testy kontraktowe dla books-service** (~40 linii pytest, `requests` na żywy
   kontener): żądanie → status + klucze ciała, w tym błędy 400/404/405/409. Zielone na
   obecnym kodzie. *Po co:* zmiana serwera ma nie ruszyć kontraktu; test to udowadnia, a nie
   „sprawdziłem ręcznie”.
3. **Zmiana (a):** `service_runtime.py` → gunicorn, 1 worker, 40 wątków; haki startowe i
   wątki w tle w `post_worker_init` (stan w pamięci musi żyć w workerze, nie w masterze);
   timeout 120 s (haki startowe przed pierwszym heartbeatem); `graceful_timeout` 5 s
   (strumienie SSE nie kończą się same). ~40 linii zmiany. Testy kontraktowe znów zielone.
4. **Pomiar przed/po na prawdziwym obrazie.** *Urealnienie #5.* Zamiast kopii serwera w
   próbce: ten sam `books-service` z obrazu Dockera sprzed zmiany (tag `before`) i po zmianie
   (tag `after`), te same scenariusze S1/S4 (+ S2/S3 na próbce). Zero dodatkowego kodu,
   mierzymy dokładnie to, co pójdzie na produkcję.
5. **Demo „jedno blokujące wywołanie”** (PDF, załącznik A): `/health` przy 10 klientach
   liczących w `def` i w `async def`. ~20 linii skryptu, 5 minut pomiaru, najlepsza lekcja o
   asyncio w całej pracy.
6. **Sprawdzenie całego systemu:** `docker compose up --build`, UI, trzy strumienie SSE,
   restart market-data (pricing ma wrócić do CONNECTED), `docker stop` < 10 s.

**Budżet kodu:** ~40 (zmiana) + ~40 (testy) + ~20 (demo). **Commity:** plan; testy; zmiana;
wyniki przed/po. **Prywatne pliki:** `09-gunicorn-od-srodka.md` (master/worker, fork, backlog,
keep-alive, graceful stop), `10-testy-kontraktowe.md`, `11-przed-po.md`,
`12-blokowanie-petli.md`.

**Do rozmowy:** dlaczego wątki w tle muszą startować po forku? Czym się różni HTTP/1.0 od
keep-alive w liczbach? Dlaczego kolejka nasłuchu 5 daje p99 równe 1 s?

---

## Faza 5 — Raport, PR, prezentacja

1. `docs/report.md` → `docs/report.pdf` (sekcje z PDF 4.2, odpowiedzi na 8 pytań z PDF 6).
2. Opis PR: decyzja w 3 zdaniach + link do raportu (wymóg PDF 7).
3. Artefakt: przeprowadzenie przez całość z interaktywnymi wykresami.
4. Prywatny `13-podsumowanie-na-rozmowe.md`: 5-minutowa opowieść + 10 pytań, które mogą paść.

---

## Pułapki znane z pilota (sprawdzamy w teście dymnym, nie odkrywamy od nowa)

| Pułapka | Objaw | Skąd wiemy |
| --- | --- | --- |
| `uvicorn --workers > 1` nie ustawia `TCP_NODELAY` | +40 ms na każde żądanie keep-alive | pilot, źródła uvicorn/asyncio |
| wsgiref: HTTP/1.0 i kolejka nasłuchu 5 | p99 ≈ 1 s, timeouty przy c ≥ 50, ładne p95 | pilot faza 4 |
| błędy poza percentylami | wariant „wygrywa” p95, gubiąc żądania | A przy c = 200: 78 % timeoutów |
| goły uvicorn (h11, asyncio) | FastAPI −14 % na `/health`; z uvloop +100 % | pilot, kontrola B-std |
| jeden rdzeń | koszt CPU na żądanie decyduje o wyniku S2 | pilot: httpx 2,0 ms vs requests 1,3 ms |
| RSS przy forku | master + worker liczone podwójnie | pilot: 153 vs 90 MB |

## Budżet całości

~450 linii kodu (bez wyników), 2 nocne runy (~2 h + ~1 h), 6 sekcji raportu,
13 prywatnych plików tur. Kolejność commitów = kolejność etapów z PDF.
