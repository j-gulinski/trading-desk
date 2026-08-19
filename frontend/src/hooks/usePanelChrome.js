import { useEffect } from 'react'

export function usePanelChrome(panelRef, onClose, { closeOnOutsideClick = true } = {}) {
  useEffect(() => {
    const panel = panelRef.current
    if (panel == null) return undefined

    function handlePointerDown(event) {
      if (panel.contains(event.target)) return
      if (
        event.target instanceof Element &&
        event.target.closest('[data-panel-trigger], .side-panel')
      ) {
        return
      }
      onClose()
    }

    function handleKeyDown(event) {
      if (event.key !== 'Escape') return
      const panels = document.querySelectorAll('.side-panel')
      if (panels.length > 0 && panels[panels.length - 1] !== panel) return
      event.preventDefault()
      onClose()
    }

    if (closeOnOutsideClick) document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      if (closeOnOutsideClick) document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [panelRef, onClose, closeOnOutsideClick])
}
