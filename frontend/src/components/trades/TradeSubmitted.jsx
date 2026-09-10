import SidePanel from '../panel/SidePanel.jsx'
import { providerLabel } from '../../config/providers.js'
import { formatShortId } from '../../domain/formatting.js'

export default function TradeSubmitted({ summary, provider, modelPriced, tradeId, onNewTrade, onClose }) {
  return (
    <SidePanel
      eyebrow="TRADE ACTION"
      title="Trade submitted"
      subtitle="The order was accepted for processing"
      dismissOnOutsideClick={false}
      onClose={onClose}
    >
      <div className="panel-form__ack" role="status">
        <span>
          {summary}
          {provider != null && <> via {providerLabel(provider)}</>}
          {modelPriced && ' · model-priced'}
          {tradeId != null && ` · trade ${formatShortId(tradeId)}`}
        </span>
      </div>
      <div className="panel-form__actions">
        <button type="button" className="panel-form__cancel" onClick={onNewTrade}>
          New trade
        </button>
        <button
          type="button"
          className="panel-form__submit"
          onClick={() => {
            window.location.hash = '/trades'
            onClose()
          }}
        >
          View in Trades
        </button>
      </div>
    </SidePanel>
  )
}
