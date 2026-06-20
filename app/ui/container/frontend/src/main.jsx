import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@uswds/uswds/css/uswds.min.css'
import '@uswds/uswds/js/uswds.min.js'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
