CREATE TABLE IF NOT EXISTS positions (
    instrument integer NOT NULL,
    book integer NOT NULL,
    quantity bigint NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (instrument, book)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id bigserial PRIMARY KEY,
    instrument integer NOT NULL,
    book integer NOT NULL,
    quantity integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (instrument, book) REFERENCES positions
);

INSERT INTO positions (instrument, book, quantity)
SELECT instrument, book, 0
FROM generate_series(0, 9999) AS instrument, generate_series(0, 99) AS book
ON CONFLICT DO NOTHING;

ANALYZE positions;
