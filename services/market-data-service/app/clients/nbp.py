from app.clients.base import ProviderClient
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

    def table_a_history(self, days):
        # NBP caps range queries at 93 days/255 tables
        return self.get(f"/exchangerates/tables/a/last/{min(days, 93)}",
                        {"format": "json"})

    def gold_price_history(self, days):
        return self.get(f"/cenyzlota/last/{min(days, 93)}", {"format": "json"})
