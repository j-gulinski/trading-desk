"""Provider packages and their common registration contract."""

from market_data_service.providers.alpha_vantage import registration as alpha_vantage
from market_data_service.providers.ecb import registration as ecb
from market_data_service.providers.eiopa import registration as eiopa
from market_data_service.providers.finnhub import registration as finnhub
from market_data_service.providers.fred import registration as fred
from market_data_service.providers.nbp import registration as nbp
from market_data_service.providers.twelve_data import registration as twelve_data

REGISTRATIONS = (finnhub, twelve_data, alpha_vantage, nbp, ecb, fred, eiopa)
BY_NAME = {provider.name: provider for provider in REGISTRATIONS}
