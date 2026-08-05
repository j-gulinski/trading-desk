const PATHS = {
  '': 'M3 12h3l2-5 3 10 2.5-7 1.8 4H21',
  generator: 'M13 2 4 14h6l-1 8 9-12h-6z',
  'trade-actions': 'M4 7h11m0 0-3-3m3 3-3 3M20 17H9m0 0 3-3m-3 3 3 3',
  'business-overview': 'M4 20V10m5 10V4m5 16v-7m5 7V8',
  'market-data': 'M4 18l5-6 4 3 7-9M20 6h-4m4 0v4',
  valuations: 'M12 3v18M7 8a5 5 0 0 1 10 0c0 3-10 2-10 5a5 5 0 0 0 10 0',
  books: 'M4 5a2 2 0 0 1 2-2h5v18H6a2 2 0 0 1-2-2zM13 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5z',
  trades: 'M4 6h16M4 12h16M4 18h10',
}

export default function RouteIcon({ path }) {
  return (
    <svg
      className="sidebar__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[path] ?? PATHS.trades} />
    </svg>
  )
}
