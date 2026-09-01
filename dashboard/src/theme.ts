import { alpha, createTheme, type PaletteMode } from '@mui/material/styles'

export type AppColorMode = PaletteMode

export function createAppTheme(mode: AppColorMode) {
  const dark = mode === 'dark'

  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? '#7CB7F5' : '#3478C8', contrastText: dark ? '#0B1220' : '#FFFFFF' },
      secondary: { main: dark ? '#AAB9CC' : '#64748B' },
      success: { main: dark ? '#65C98A' : '#288A52' },
      warning: { main: dark ? '#D8A958' : '#B7791F' },
      error: { main: dark ? '#E57373' : '#C24141' },
      background: { default: dark ? '#0C1422' : '#F5F7FA', paper: dark ? '#121D2C' : '#FFFFFF' },
      text: { primary: dark ? '#E8EEF6' : '#172033', secondary: dark ? '#8D9CAF' : '#64748B' },
      divider: alpha(dark ? '#C8D4E3' : '#334155', dark ? 0.09 : 0.11),
    },
    shape: { borderRadius: 12 },
    typography: {
      fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      h4: { fontWeight: 680, letterSpacing: '-0.035em' },
      h5: { fontWeight: 660, letterSpacing: '-0.025em' },
      h6: { fontWeight: 650, letterSpacing: '-0.015em' },
      button: { textTransform: 'none', fontWeight: 620 },
    },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            border: `1px solid ${alpha(dark ? '#C8D4E3' : '#334155', dark ? 0.085 : 0.1)}`,
            boxShadow: dark ? 'none' : '0 1px 2px rgba(15, 23, 42, 0.035)',
          },
        },
      },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiChip: { styleOverrides: { root: { fontWeight: 620 } } },
      MuiTableCell: {
        styleOverrides: {
          root: { borderColor: alpha(dark ? '#C8D4E3' : '#334155', dark ? 0.075 : 0.09) },
        },
      },
    },
  })
}
