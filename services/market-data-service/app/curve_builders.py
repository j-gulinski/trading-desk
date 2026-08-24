from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.clients.base import ProviderDataError
from app.config import NBP_REFERENCE_RATE_PERCENT
from shared.curves import build_curve_point, build_curve_set
from shared.functions import utcnow
from shared.providers import ECB, FRED, NBP
from shared.quotes import as_decimal

USD_TREASURY = "USD_TREASURY"
EUR_GOV_AAA = "EUR_GOV_AAA"
EUR_GOV_ALL = "EUR_GOV_ALL"
PLN_REF = "PLN_REF"
PLN_NBP_BASE = "PLN_NBP_BASE"

DGS_SERIES = (
    ("1M", Decimal("0.083333"), "DGS1MO"),
    ("3M", Decimal("0.25"), "DGS3MO"),
    ("6M", Decimal("0.5"), "DGS6MO"),
    ("1Y", Decimal(1), "DGS1"),
    ("2Y", Decimal(2), "DGS2"),
    ("3Y", Decimal(3), "DGS3"),
    ("5Y", Decimal(5), "DGS5"),
    ("7Y", Decimal(7), "DGS7"),
    ("10Y", Decimal(10), "DGS10"),
    ("20Y", Decimal(20), "DGS20"),
    ("30Y", Decimal(30), "DGS30"),
)
# daily series publish with a 1-2 business-day lag; a fresh date can still hold "."
FRED_DAILY_LOOKBACK = 7
# monthly OECD series lag ~2 months
FRED_MONTHLY_LOOKBACK = 4

PLN_SHORT_SERIES = "IR3TIB01PLM156N"
PLN_LONG_SERIES = "IRLTLT01PLM156N"
PLN_SHORT_TENOR = Decimal("0.25")
PLN_LONG_TENOR = Decimal(10)
PLN_DERIVED_TENORS = (("1Y", Decimal(1)), ("2Y", Decimal(2)), ("5Y", Decimal(5)))
PLN_PROXY_TENORS = (
    ("3M", Decimal("0.25")),
    ("1Y", Decimal(1)),
    ("2Y", Decimal(2)),
    ("5Y", Decimal(5)),
    ("10Y", Decimal(10)),
)

ECB_YC_TENORS = (
    ("3M", Decimal("0.25"), "SR_3M"),
    ("6M", Decimal("0.5"), "SR_6M"),
    ("1Y", Decimal(1), "SR_1Y"),
    ("2Y", Decimal(2), "SR_2Y"),
    ("3Y", Decimal(3), "SR_3Y"),
    ("5Y", Decimal(5), "SR_5Y"),
    ("7Y", Decimal(7), "SR_7Y"),
    ("10Y", Decimal(10), "SR_10Y"),
    ("15Y", Decimal(15), "SR_15Y"),
    ("20Y", Decimal(20), "SR_20Y"),
    ("30Y", Decimal(30), "SR_30Y"),
)
ECB_YC_DATASETS = {EUR_GOV_AAA: "G_N_A", EUR_GOV_ALL: "G_N_C"}

WARSAW = ZoneInfo("Europe/Warsaw")


def _as_of(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").date()


def _fred_latest(client, record_request, series_id, lookback):
    record_request()
    payload = client.latest_observations(series_id, lookback)
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not observations:
        raise ProviderDataError(FRED, f"{series_id} returned no observations")
    for observation in observations:
        value = observation.get("value")
        if value not in (None, "", "."):
            return _as_of(observation["date"]), as_decimal(value), payload
    raise ProviderDataError(FRED, f"{series_id} carries only missing values")


def build_usd_treasury(client, record_request):
    points = []
    raw = {}
    for label, years, series_id in DGS_SERIES:
        try:
            as_of, rate, payload = _fred_latest(
                client, record_request, series_id, FRED_DAILY_LOOKBACK
            )
        except ProviderDataError:
            raw[series_id] = {"error": "no usable observation"}
            continue
        raw[series_id] = payload
        points.append(build_curve_point(label, years, rate, series_id, as_of))
    if not points:
        raise ProviderDataError(FRED, "no DGS series returned a value")
    return build_curve_set(
        provider=FRED,
        curve_name=USD_TREASURY,
        curve_type="GOV_ZERO",
        currency="USD",
        as_of_date=min(point.source_as_of for point in points),
        received_at=utcnow(),
        points=points,
        raw_payload=raw,
    )


def _interpolate(short_rate, long_rate, short_tenor, long_tenor, tenor):
    span = long_tenor - short_tenor
    return short_rate + (long_rate - short_rate) * (tenor - short_tenor) / span


def build_pln_ref(client, record_request):
    short_as_of, short_rate, short_raw = _fred_latest(
        client, record_request, PLN_SHORT_SERIES, FRED_MONTHLY_LOOKBACK
    )
    long_as_of, long_rate, long_raw = _fred_latest(
        client, record_request, PLN_LONG_SERIES, FRED_MONTHLY_LOOKBACK
    )
    points = [
        build_curve_point("3M", PLN_SHORT_TENOR, short_rate, PLN_SHORT_SERIES, short_as_of),
        build_curve_point("10Y", PLN_LONG_TENOR, long_rate, PLN_LONG_SERIES, long_as_of),
    ]
    for label, years in PLN_DERIVED_TENORS:
        rate = _interpolate(short_rate, long_rate, PLN_SHORT_TENOR, PLN_LONG_TENOR, years)
        points.append(build_curve_point(label, years, rate))
    return build_curve_set(
        provider=FRED,
        curve_name=PLN_REF,
        curve_type="COMPOSITE_REF",
        currency="PLN",
        as_of_date=min(short_as_of, long_as_of),
        received_at=utcnow(),
        points=points,
        raw_payload={PLN_SHORT_SERIES: short_raw, PLN_LONG_SERIES: long_raw},
        index_tenor="3M",
    )


def _ecb_tenor_rows(payload):
    rows = {}
    for row in payload.get("rows", []):
        code = row.get("DATA_TYPE_FM") or row.get("KEY", "").rsplit(".", 1)[-1]
        if code and row.get("OBS_VALUE"):
            rows[code] = row
    return rows


def make_ecb_curve_builder(curve_name):
    dataset_key = ECB_YC_DATASETS[curve_name]

    def build(client, record_request):
        record_request()
        payload = client.yield_curve(dataset_key, [code for _, _, code in ECB_YC_TENORS])
        by_code = _ecb_tenor_rows(payload)
        points = []
        for label, years, code in ECB_YC_TENORS:
            row = by_code.get(code)
            if row is None:
                continue
            points.append(build_curve_point(
                label, years, row["OBS_VALUE"],
                row.get("KEY") or f"YC {dataset_key} {code}",
                _as_of(row["TIME_PERIOD"]),
            ))
        if not points:
            raise ProviderDataError(ECB, f"YC {dataset_key} returned no observations")
        return build_curve_set(
            provider=ECB,
            curve_name=curve_name,
            curve_type="GOV_ZERO",
            currency="EUR",
            as_of_date=min(point.source_as_of for point in points),
            received_at=utcnow(),
            points=points,
            raw_payload=payload,
        )

    return build


def build_pln_nbp_base(client=None, record_request=None):
    rate = as_decimal(NBP_REFERENCE_RATE_PERCENT)
    points = [build_curve_point(label, years, rate) for label, years in PLN_PROXY_TENORS]
    return build_curve_set(
        provider=NBP,
        curve_name=PLN_NBP_BASE,
        curve_type="POLICY_PROXY",
        currency="PLN",
        as_of_date=utcnow().astimezone(WARSAW).date(),
        received_at=utcnow(),
        points=points,
        raw_payload={
            "source": "configuration",
            "parameter": "NBP_REFERENCE_RATE_PERCENT",
            "value": str(rate),
            "note": "NBP publishes its reference rate on nbp.pl but not through the API",
        },
    )
