def book_to_dict(book) -> dict:
    return {
        "book_id": book.book_id,
        "name": book.name,
        "description": book.description,
        "expected_asset_class": book.expected_asset_class,
        "is_active": book.is_active,
        "created_at": book.created_at,
        "updated_at": book.updated_at,
        "created_by": book.created_by,
        "updated_by": book.updated_by,
    }
