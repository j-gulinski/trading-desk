export default function TradeStatusTabs({ value, openCount, closedCount, totalCount, onChange }) {
  const locked = typeof onChange !== 'function'

  return (
    <div className="trade-tabs" role="group" aria-label="Trade lifecycle">
      <button
        type="button"
        className="trade-tabs__button"
        aria-pressed={value === 'OPEN'}
        disabled={locked}
        onClick={() => onChange?.('OPEN')}
      >
        <span>Open</span>
        <span className="trade-tabs__count">{openCount}</span>
      </button>
      <button
        type="button"
        className="trade-tabs__button"
        aria-pressed={value === 'BOTH'}
        disabled={locked}
        onClick={() => onChange?.('BOTH')}
      >
        <span>Both</span>
        <span className="trade-tabs__count">{totalCount}</span>
      </button>
      <button
        type="button"
        className="trade-tabs__button"
        aria-pressed={value === 'CLOSED'}
        disabled={locked}
        onClick={() => onChange?.('CLOSED')}
      >
        <span>Closed</span>
        <span className="trade-tabs__count">{closedCount}</span>
      </button>
    </div>
  )
}
