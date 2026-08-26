import { useRef } from 'react'
import { usePanelChrome } from '../../hooks/usePanelChrome.js'
import { usePanelCoordinator } from '../../layout/panelContext.js'

export default function SidePanel({
  eyebrow,
  title,
  subtitle,
  headActions,
  notice,
  tabs,
  footer,
  wide = false,
  roomy = false,
  compact = false,
  bodyClassName = '',
  dismissOnOutsideClick = true,
  onClose,
  children,
}) {
  const panelRef = useRef(null)
  const { switchingPanel } = usePanelCoordinator()
  const suppressEntryAnimation = useRef(switchingPanel)

  usePanelChrome(panelRef, onClose, { closeOnOutsideClick: dismissOnOutsideClick })

  return (
    <aside
      ref={panelRef}
      className={`side-panel${wide ? ' side-panel--wide' : ''}${
        roomy ? ' side-panel--roomy' : ''
      }${
        compact ? ' side-panel--compact' : ''
      }${
        suppressEntryAnimation.current ? ' side-panel--no-enter' : ''
      }`}
    >
      <header className="side-panel__head">
        <div className="side-panel__heading">
          <span className="side-panel__eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="side-panel__head-actions">
          {headActions}
          <button
            type="button"
            className="side-panel__close"
            onClick={onClose}
            aria-label="Close panel"
          >
            ×
          </button>
        </div>
      </header>

      {notice}
      {tabs}

      <div className={`side-panel__body${bodyClassName ? ` ${bodyClassName}` : ''}`}>
        {children}
      </div>

      {footer && <footer className="side-panel__footer">{footer}</footer>}
    </aside>
  )
}
