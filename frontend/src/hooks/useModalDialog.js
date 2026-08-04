import { useEffect, useRef } from 'react'

export function useModalDialog() {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  function close() {
    dialogRef.current?.close()
  }

  function closeOnBackdrop(event) {
    if (event.target === event.currentTarget) close()
  }

  return { dialogRef, close, closeOnBackdrop }
}
