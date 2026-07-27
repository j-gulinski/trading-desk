import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { MarketFeedProvider } from './providers/MarketFeedProvider.jsx'
import './styles/main.scss'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MarketFeedProvider>
      <App />
    </MarketFeedProvider>
  </StrictMode>
)
