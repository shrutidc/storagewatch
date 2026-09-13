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
import Settings from './pages/Settings.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID

ReactDOM.createRoot(document.getElementById('root')).render(
  <Auth0Provider
    domain={domain}
    clientId={clientId}
    authorizationParams={{
      redirect_uri: window.location.origin,
      // Requesting an audience is what makes Auth0 issue a verifiable JWT
      // rather than an opaque token, which is what lets the backend check it.
      // It must name an API registered in the tenant (Applications -> APIs).
      audience: import.meta.env.VITE_AUTH0_AUDIENCE,
    }}
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
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </Auth0Provider>,
)
