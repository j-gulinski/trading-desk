from app.providers.base import ProviderClient
from shared.providers import NBP


class NbpClient(ProviderClient):
    provider = NBP
    base_url = "https://api.nbp.pl/api"

    def classify_body(self, payload):
        pass

    def table_a(self):
        return self.get("/exchangerates/tables/a", {"format": "json"})

    def gold_price(self):
        return self.get("/cenyzlota", {"format": "json"})
