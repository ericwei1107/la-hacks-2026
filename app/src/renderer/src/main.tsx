import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './fonts'
import './styles.css'
import { IntegrationCheck } from './IntegrationCheck'
import { MainWindow } from './main-window/MainWindow'
import { ServicesProvider } from './services'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ServicesProvider>{window.location.hash === '#integration' ? <IntegrationCheck /> : <MainWindow />}</ServicesProvider>
  </StrictMode>
)
