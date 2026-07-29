import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { FeedProvider } from './providers/FeedProvider.jsx'
import './styles/main.scss'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <FeedProvider>
      <App />
    </FeedProvider>
  </StrictMode>
)
