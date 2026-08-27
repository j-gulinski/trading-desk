#!/usr/bin/env bash
set -euo pipefail

MARKET_DATA_URL=${MARKET_DATA_URL:-http://localhost:8001}
PRICING_URL=${PRICING_URL:-http://localhost:8002}
BLOTTER_URL=${BLOTTER_URL:-http://localhost:8006}
ACTIONS_URL=${ACTIONS_URL:-http://localhost:8008}
IDEMPOTENCY_REQUESTS=${IDEMPOTENCY_REQUESTS:-20}
SSE_CLIENTS_PER_STREAM=${SSE_CLIENTS_PER_STREAM:-20}
BOARD_READS=${BOARD_READS:-200}
PARALLELISM=${PARALLELISM:-20}

for command in curl jq docker perl xargs; do
  command -v "$command" >/dev/null || {
    printf 'missing required command: %s\n' "$command" >&2
    exit 1
  }
done

book_id=$(curl -fsS "$BLOTTER_URL/books/summary" |
  jq -r '.[] | select(.expected_asset_class=="EQUITY" and .is_active==true) | .book_id' |
  head -1)
price=$(curl -fsS "$MARKET_DATA_URL/quotes/ALPHA_VANTAGE/AAPL" | jq -r '.mid')
if [[ -z "$book_id" || -z "$price" || "$price" == null ]]; then
  printf 'requires an active EQUITY book and a stored Alpha AAPL quote\n' >&2
  exit 1
fi

request_id="phase6-idem-$(date +%s)"
payload=$(jq -nc \
  --arg request "$request_id" \
  --arg book "$book_id" \
  --arg price "$price" \
  '{action_type:"OPEN_TRADE",client_request_id:$request,book_id:$book,
    asset_class:"EQUITY",symbol:"AAPL",side:"BUY",quantity:1,
    market_data_provider:"ALPHA_VANTAGE",client_seen_price:$price,
    source:"TRADING_TICKET"}')

printf '%s\n' '--- concurrent ticket idempotency'
start=$(perl -MTime::HiRes=time -e 'print time')
responses=$(seq 1 "$IDEMPOTENCY_REQUESTS" |
  xargs -P "$PARALLELISM" -I '{}' sh -c \
    'curl -fsS -X POST "$1/trade-actions" -H "Content-Type: application/json" -d "$2"; printf "\n"' \
    sh "$ACTIONS_URL" "$payload")
end=$(perl -MTime::HiRes=time -e 'print time')
trade_id=$(printf '%s\n' "$responses" | jq -sr '.[0].trade_id')
printf '%s\n' "$responses" | jq -s --arg start "$start" --arg end "$end" \
  '{requests:length,unique_trade_ids:([.[].trade_id]|unique),
    replays:([.[]|select(.idempotent_replay==true)]|length),
    elapsed_seconds:(($end|tonumber)-($start|tonumber))}'
sleep 2
docker exec postgres sh -lc \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select count(*),min(status),min(source),min(market_data_provider) from trades where client_request_id='$request_id';\""
close_payload=$(jq -nc --arg trade "$trade_id" --arg price "$price" \
  '{action_type:"CLOSE_TRADE",client_request_id:("close-"+$trade),trade_id:$trade,
    client_seen_price:$price,close_reason:"PHASE6_STRESS_CLEANUP"}')
curl -fsS -X POST "$ACTIONS_URL/trade-actions" \
  -H 'Content-Type: application/json' -d "$close_payload" | jq .

printf '%s\n' '--- baseline docker stats'
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \
  market-data-service pricing-service frontend
printf '%s\n' '--- bounded SSE fan-out'
for _ in $(seq 1 "$SSE_CLIENTS_PER_STREAM"); do
  curl -fsSN --max-time 3 "$MARKET_DATA_URL/market-data/stream" >/dev/null 2>&1 &
done
for _ in $(seq 1 "$SSE_CLIENTS_PER_STREAM"); do
  curl -fsSN --max-time 3 "$PRICING_URL/valuation-stream" >/dev/null 2>&1 &
done
sleep 1
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \
  market-data-service pricing-service frontend
wait || true
printf 'fanout_connections_completed=%s\n' "$((SSE_CLIENTS_PER_STREAM * 2))"

printf '%s\n' '--- active-board read burst (no provider calls)'
start=$(perl -MTime::HiRes=time -e 'print time')
codes=$(seq 1 "$BOARD_READS" |
  xargs -P "$PARALLELISM" -I '{}' sh -c \
    'curl -sS -o /dev/null -w "%{http_code}\n" "$1/market-data/quotes"' \
    sh "$MARKET_DATA_URL")
end=$(perl -MTime::HiRes=time -e 'print time')
printf '%s\n' "$codes" | sort | uniq -c
perl -e '$s=$ARGV[0];$e=$ARGV[1];$n=$ARGV[2];$d=$e-$s;
  printf("requests=%d elapsed_seconds=%.3f requests_per_second=%.1f\n",$n,$d,$n/$d)' \
  "$start" "$end" "$BOARD_READS"
curl -fsS "$MARKET_DATA_URL/market-data/quotes" |
  jq '{provider_rows:length,symbols:([.[].symbol]|unique|length)}'

printf '%s\n' '--- valuation sampling and table growth'
docker exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "with samples as (select trade_id,valuation_time,lag(valuation_time) over (partition by trade_id order by valuation_time) prior from valuations where valuation_time > now()-interval '\''30 minutes'\'' and coalesce((valuation_payload->>'\''final'\'')::boolean,false)=false) select '\''sample_intervals'\'',count(*),round(min(extract(epoch from valuation_time-prior))::numeric,3) from samples where prior is not null; select '\''audit_logs'\'',count(*) from audit_logs union all select '\''snapshots'\'',count(*) from market_data_snapshots union all select '\''spot_prices'\'',count(*) from market_data_spot_prices union all select '\''trades'\'',count(*) from trades union all select '\''valuations'\'',count(*) from valuations order by 1; select '\''alpha_ledger'\'',requests,credits from provider_request_ledgers where provider='\''ALPHA_VANTAGE'\'' and usage_date=current_date;"'
