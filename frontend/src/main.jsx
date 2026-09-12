import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Auth0Provider } from '@auth0/auth0-react'
import App from './App.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Volumes from './pages/Volumes.jsx'
import Disks from './pages/Disks.jsx'
import Apfs from './pages/Apfs.jsx'
import Performance from './pages/Performance.jsx'
import Alerts from './pages/Alerts.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID

ReactDOM.createRoot(document.getElementById('root')).render(
  <Auth0Provider
    domain={domain}
    clientId={clientId}
    redirectUri={window.location.origin}
    audience={import.meta.env.VITE_AUTH0_AUDIENCE}
  >
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Dashboard />} />
          <Route path="volumes" element={<Volumes />} />
          <Route path="disks" element={<Disks />} />
          <Route path="apfs" element={<Apfs />} />
          <Route path="performance" element={<Performance />} />
          <Route path="alerts" element={<Alerts />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </Auth0Provider>,
)
