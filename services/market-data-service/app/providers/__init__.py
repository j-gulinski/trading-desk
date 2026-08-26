"""Provider packages and their common registration contract."""

from app.providers.ecb import registration as ecb
from app.providers.eiopa import registration as eiopa
from app.providers.finnhub import registration as finnhub
from app.providers.fred import registration as fred
from app.providers.nbp import registration as nbp
from app.providers.twelve_data import registration as twelve_data

REGISTRATIONS = (finnhub, twelve_data, nbp, ecb, fred, eiopa)
BY_NAME = {provider.name: provider for provider in REGISTRATIONS}
