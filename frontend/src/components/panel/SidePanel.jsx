import { useId, useRef } from 'react'
import { usePanelChrome } from '../../hooks/usePanelChrome.js'

export default function SidePanel({
  eyebrow,
  title,
  subtitle,
  headActions,
  notice,
  tabs,
  footer,
  wide = false,
  closeLabel = 'Close panel',
  onClose,
  children,
}) {
  const panelRef = useRef(null)
  const titleId = useId()

  usePanelChrome(panelRef, onClose)

  return (
    <aside
      ref={panelRef}
      className={`side-panel${wide ? ' side-panel--wide' : ''}`}
      role="region"
      aria-labelledby={titleId}
    >
      <header className="side-panel__head">
        <div className="side-panel__heading">
          <span className="side-panel__eyebrow">{eyebrow}</span>
          <h2 id={titleId}>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="side-panel__head-actions">
          {headActions}
          <button
            type="button"
            className="side-panel__close"
            aria-label={closeLabel}
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </header>

      {notice}
      {tabs}

      <div className="side-panel__body">{children}</div>

      {footer && <footer className="side-panel__footer">{footer}</footer>}
    </aside>
  )
}
