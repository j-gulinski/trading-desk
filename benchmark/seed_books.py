# Gives S4 a fixed data set: 20 books, created once through the books-service repository.
from books_service import repository
from desk_domain.instruments import INSTRUMENT_TYPES

BOOKS = 20

existing = {book["name"] for book in repository.list_books()}
asset_classes = sorted(INSTRUMENT_TYPES)
for i in range(1, BOOKS + 1):
    name = f"Benchmark book {i:02d}"
    if name not in existing:
        repository.create_book({
            "name": name,
            "description": "benchmark sample",
            "expected_asset_class": asset_classes[i % len(asset_classes)],
        })
print(f"{len(repository.list_books())} books")
