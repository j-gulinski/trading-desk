import csv
import io

from app.providers.base import ProviderClient, ProviderDataError
from shared.providers import ECB


class EcbClient(ProviderClient):
    provider = ECB
    base_url = "https://data-api.ecb.europa.eu/service"

    def decode_body(self, body):
        text = body.decode("utf-8-sig")
        return {"format": "csvdata", "rows": list(csv.DictReader(io.StringIO(text)))}

    def classify_body(self, payload):
        if not payload.get("rows"):
            raise ProviderDataError(
                self.provider, "empty csvdata response", response=payload
            )

    def exchange_rates(self, currency_codes):
        series = f"D.{'+'.join(sorted(currency_codes))}.EUR.SP00.A"
        return self.get(
            f"/data/EXR/{series}",
            {"format": "csvdata", "lastNObservations": 1},
        )

    def yield_curve(self, dataset_key, tenor_codes):
        series = f"B.U2.EUR.4F.{dataset_key}.SV_C_YM.{'+'.join(tenor_codes)}"
        return self.get(
            f"/data/YC/{series}", {"format": "csvdata", "lastNObservations": 1}
        )
