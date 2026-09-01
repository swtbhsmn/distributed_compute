import { StrictMode, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { CssBaseline, ThemeProvider } from '@mui/material'
import App from './App'
import { createAppTheme, type AppColorMode } from './theme'
import './index.css'

const colorModeKey = 'compute-grid-color-mode'

function initialColorMode(): AppColorMode {
  const saved = localStorage.getItem(colorModeKey)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function DashboardRoot() {
  const [colorMode, setColorMode] = useState<AppColorMode>(initialColorMode)
  const theme = useMemo(() => createAppTheme(colorMode), [colorMode])

  function toggleColorMode() {
    setColorMode((current) => {
      const next = current === 'dark' ? 'light' : 'dark'
      localStorage.setItem(colorModeKey, next)
      return next
    })
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App colorMode={colorMode} onToggleColorMode={toggleColorMode} />
    </ThemeProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DashboardRoot />
  </StrictMode>,
)
