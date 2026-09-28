from market_data_service.providers.base import ProviderClient
from market_data_service.config import NBP_BASE_URL
from desk_domain.providers import NBP


class NbpClient(ProviderClient):
    provider = NBP
    base_url = NBP_BASE_URL

    def table_a(self):
        return self.get("/exchangerates/tables/a", {"format": "json"})

    def gold_price(self):
        return self.get("/cenyzlota", {"format": "json"})
