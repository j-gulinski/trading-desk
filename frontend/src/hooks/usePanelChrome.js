import { useEffect } from 'react'

export function usePanelChrome(panelRef, onClose) {
  useEffect(() => {
    const panel = panelRef.current
    if (panel == null) return undefined

    function handlePointerDown(event) {
      if (panel.contains(event.target)) return
      if (event.target instanceof Element && event.target.closest('[data-panel-trigger]')) return
      onClose()
    }

    function handleKeyDown(event) {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onClose()
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [panelRef, onClose])
}
