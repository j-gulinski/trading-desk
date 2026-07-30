export function buildCloseTradeIntent(tradeId, closePrice) {
  return {
    action_type: 'CLOSE_TRADE',
    trade_id: tradeId,
    close_price: Number.isFinite(closePrice) ? closePrice : null,
    close_reason: 'MANUAL_CLOSE',
    client_request_id: crypto.randomUUID(),
  }
}
