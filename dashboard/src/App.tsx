import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  Alert,
  AppBar,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Tooltip,
  Typography,
  alpha,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import {
  Activity,
  Boxes,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Gauge,
  LayoutDashboard,
  LogOut,
  MemoryStick,
  Menu,
  Moon,
  Network,
  Plus,
  RefreshCw,
  Server,
  Smartphone,
  Sun,
  Timer,
  TriangleAlert,
  UsersRound,
  type LucideIcon,
} from 'lucide-react'
import { ApiError, createJob, loadDashboard } from './api'
import type { AppColorMode } from './theme'
import type { Job, JobStatus, JobType, NewJob, Worker } from './types'

const drawerWidth = 248
const tokenKey = 'compute-grid-token'
const urlKey = 'compute-grid-url'

type View = 'overview' | 'workers' | 'jobs'

const navItems: { id: View; label: string; icon: LucideIcon }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'workers', label: 'Workers', icon: Server },
  { id: 'jobs', label: 'Jobs', icon: Boxes },
]

function formatBytes(bytes: number): string {
  if (bytes <= 0) return 'Unavailable'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** exponent).toFixed(exponent > 2 ? 1 : 0)} ${units[exponent]}`
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

function shortId(value: string): string {
  return `${value.slice(0, 8)}…`
}

function jobProgress(job: Job): number {
  return job.total_tasks ? (job.completed_tasks / job.total_tasks) * 100 : 0
}

function formatDuration(milliseconds: number): string {
  const totalMilliseconds = Math.max(0, Math.floor(milliseconds))
  if (totalMilliseconds < 1000) return `${totalMilliseconds}ms`
  const totalSeconds = Math.floor(totalMilliseconds / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const remainderMilliseconds = totalMilliseconds % 1000
  const millisecondPart = remainderMilliseconds ? ` ${String(remainderMilliseconds).padStart(3, '0')}ms` : ''
  if (hours) return `${hours}h ${minutes}m ${seconds}s${millisecondPart}`
  if (minutes) return `${minutes}m ${seconds}s${millisecondPart}`
  return `${seconds}s${millisecondPart}`
}

function jobDuration(job: Job, now: number): string {
  if (!job.started_at) return 'Waiting'
  const started = Date.parse(job.started_at)
  const ended = job.completed_at ? Date.parse(job.completed_at) : now
  return formatDuration(ended - started)
}

const statusColors: Record<JobStatus, 'default' | 'primary' | 'success' | 'error'> = {
  pending: 'default', running: 'primary', completed: 'success', failed: 'error',
}

function StatusChip({ status }: { status: JobStatus }) {
  return <Chip size="small" variant="outlined" color={statusColors[status]} label={status} sx={{ textTransform: 'capitalize' }} />
}

function StatCard({
  label, value, detail, icon: Icon,
}: { label: string; value: string; detail: string; icon: LucideIcon }) {
  return (
    <Card sx={{ minWidth: 0 }}>
      <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography color="text.secondary" variant="body2" fontWeight={650}>{label}</Typography>
            <Typography variant="h4" sx={{ mt: 1, fontSize: { xs: '1.85rem', md: '2.15rem' } }}>{value}</Typography>
          </Box>
          <Avatar variant="rounded" sx={{ bgcolor: 'action.hover', color: 'text.secondary', width: 40, height: 40 }}>
            <Icon size={19} strokeWidth={1.9} />
          </Avatar>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1.3, display: 'block' }}>{detail}</Typography>
      </CardContent>
    </Card>
  )
}

function SectionTitle({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} gap={1.5} mb={2}>
      <Box>
        <Typography variant="h6">{title}</Typography>
        <Typography variant="body2" color="text.secondary">{description}</Typography>
      </Box>
      {action}
    </Stack>
  )
}

function EmptyState({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) {
  return (
    <Stack alignItems="center" justifyContent="center" py={7} textAlign="center">
      <Avatar sx={{ bgcolor: 'action.hover', color: 'text.secondary', mb: 2 }}><Icon size={21} /></Avatar>
      <Typography fontWeight={700}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" maxWidth={360}>{description}</Typography>
    </Stack>
  )
}

function WorkerCard({ worker }: { worker: Worker }) {
  const [expanded, setExpanded] = useState(false)
  const details = [
    { label: 'Worker ID', value: worker.worker_id, mono: true },
    { label: 'Operating system', value: `${worker.os_name} ${worker.os_release}` },
    { label: 'Benchmark', value: `${formatCompact(worker.benchmark.operations_per_second)} ops/s` },
    { label: 'Benchmark time', value: `${(worker.benchmark.elapsed_seconds * 1000).toFixed(1)} ms` },
    { label: 'Current task', value: worker.current_task_id ?? 'Idle', mono: true },
    { label: 'Registered', value: formatDate(worker.registered_at) },
    { label: 'Last seen', value: formatDate(worker.last_seen) },
  ]

  return (
    <Card variant="outlined" sx={{ boxShadow: 'none' }}>
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr) auto', md: 'minmax(170px, .75fr) minmax(300px, 2fr) auto' }, gridTemplateAreas: { xs: '"device actions" "metrics metrics"', md: '"device metrics actions"' }, alignItems: 'center', gap: { xs: 1.25, md: 1.5 } }}>
          <Stack gridArea="device" direction="row" gap={1.25} alignItems="center" minWidth={0}>
            <Avatar variant="rounded" sx={{ bgcolor: 'action.hover', color: 'text.secondary', width: 38, height: 38 }}>
              {worker.os_name.toLowerCase().includes('android') ? <Smartphone size={21} /> : <Server size={21} />}
            </Avatar>
            <Box minWidth={0}>
              <Typography variant="body2" fontWeight={720} noWrap>{worker.device_name}</Typography>
              <Typography variant="caption" color="text.secondary" noWrap display="block">{worker.node} · {worker.os_name}</Typography>
            </Box>
          </Stack>
          <Stack gridArea="actions" direction="row" alignItems="center" justifyContent="flex-end" gap={0.7}>
            <Box width={7} height={7} borderRadius="50%" bgcolor={worker.online ? 'success.main' : 'text.disabled'} />
            <Typography variant="caption" color={worker.online ? 'text.primary' : 'text.secondary'} sx={{ display: { xs: 'none', sm: 'block' } }}>{worker.online ? 'Online' : 'Offline'}</Typography>
            <Tooltip title={expanded ? 'Hide details' : 'Show details'}>
              <IconButton size="small" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} aria-label={expanded ? 'Hide worker details' : 'Show worker details'}>
                <ChevronDown size={17} style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 180ms ease' }} />
              </IconButton>
            </Tooltip>
          </Stack>
        <Box gridArea="metrics" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' }, gap: 0.75 }}>
          {[
            { icon: Cpu, value: `${worker.logical_cpu_cores}`, label: 'Cores' },
            { icon: MemoryStick, value: formatBytes(worker.available_ram_bytes), label: 'Free RAM' },
            { icon: Gauge, value: `${worker.cpu_usage_percent.toFixed(0)}%`, label: 'CPU' },
          ].map((metric) => (
            <Box key={metric.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, bgcolor: 'action.hover', borderRadius: 2, px: 1.1, py: 0.75, minWidth: 0, minHeight: 44 }}>
              <Stack direction="row" alignItems="center" gap={0.75} minWidth={0} color="text.secondary">
                <metric.icon size={16} strokeWidth={1.8} />
                <Typography variant="caption" color="inherit" noWrap>{metric.label}</Typography>
              </Stack>
              <Typography variant="caption" fontWeight={720} color="text.primary" noWrap textAlign="right">{metric.value}</Typography>
            </Box>
          ))}
        </Box>
        </Box>
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <Divider sx={{ my: 1.5 }} />
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1.25 }}>
            {details.map((detail) => (
              <Box key={detail.label} minWidth={0}>
                <Typography variant="caption" color="text.secondary" display="block" mb={0.35}>{detail.label}</Typography>
                <Typography variant="body2" fontWeight={600} fontFamily={detail.mono ? 'monospace' : 'inherit'} sx={{ overflowWrap: 'anywhere' }}>{detail.value}</Typography>
              </Box>
            ))}
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  )
}

function WorkerList({ workers }: { workers: Worker[] }) {
  if (!workers.length) return <EmptyState icon={Server} title="No workers registered" description="Start a worker with this coordinator URL and it will appear here automatically." />
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'repeat(2, 1fr)' }, gap: 2 }}>
      {workers.map((worker) => <WorkerCard key={worker.worker_id} worker={worker} />)}
    </Box>
  )
}

function JobRow({ job, now }: { job: Job; now: number }) {
  const [expanded, setExpanded] = useState(false)
  const workers = job.workers ?? []
  const workerCount = job.worker_count ?? workers.length

  return (
    <Fragment>
      <TableRow hover>
        <TableCell>
          <Typography variant="body2" fontWeight={700}>{job.job_type === 'prime_count' ? 'Prime count' : 'Sum of squares'}</Typography>
          <Tooltip title={job.job_id}><Typography variant="caption" color="text.secondary" fontFamily="monospace">{shortId(job.job_id)}</Typography></Tooltip>
        </TableCell>
        <TableCell><StatusChip status={job.status} /></TableCell>
        <TableCell><Typography variant="body2" fontFamily="monospace">{formatCompact(job.start)} → {formatCompact(job.end)}</Typography></TableCell>
        <TableCell>
          <Stack direction="row" justifyContent="space-between" mb={0.7}>
            <Typography variant="caption" color="text.secondary">{job.completed_tasks}/{job.total_tasks} tasks</Typography>
            <Typography variant="caption" fontWeight={700}>{jobProgress(job).toFixed(0)}%</Typography>
          </Stack>
          <LinearProgress variant="determinate" value={jobProgress(job)} color={job.status === 'failed' ? 'error' : 'primary'} sx={{ height: 6, borderRadius: 10, bgcolor: 'action.hover' }} />
        </TableCell>
        <TableCell>
          <Button
            size="small"
            variant="text"
            disabled={!workerCount}
            startIcon={<UsersRound size={16} />}
            endIcon={<ChevronDown size={15} style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 180ms ease' }} />}
            onClick={() => setExpanded((value) => !value)}
            sx={{ color: workerCount ? 'text.primary' : 'text.disabled', whiteSpace: 'nowrap' }}
          >
            {workerCount} {workerCount === 1 ? 'worker' : 'workers'}
          </Button>
        </TableCell>
        <TableCell>
          <Stack direction="row" alignItems="center" gap={0.7} color={job.status === 'running' ? 'primary.main' : 'text.secondary'}>
            <Timer size={15} />
            <Typography variant="body2" fontWeight={650} color="text.primary">{jobDuration(job, now)}</Typography>
          </Stack>
        </TableCell>
        <TableCell>
          {job.error ? <Tooltip title={job.error}><Box color="error.main" display="inline-flex"><TriangleAlert size={18} /></Box></Tooltip> : <Typography variant="body2" fontWeight={700}>{job.result === null ? '—' : formatCompact(job.result)}</Typography>}
        </TableCell>
        <TableCell><Typography variant="caption" color="text.secondary">{formatDate(job.created_at)}</Typography></TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={8} sx={{ py: 0, borderBottom: expanded ? undefined : 0 }}>
          <Collapse in={expanded} timeout="auto" unmountOnExit>
            <Box sx={{ py: 2 }}>
              <Typography variant="subtitle2" mb={1.25}>Worker contribution</Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' }, gap: 1 }}>
                {workers.map((worker) => (
                  <Box key={worker.worker_id} sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.25, p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 2, bgcolor: 'action.hover' }}>
                    <Avatar variant="rounded" sx={{ width: 34, height: 34, bgcolor: 'background.paper', color: 'text.secondary' }}><Server size={17} /></Avatar>
                    <Box minWidth={130} flex={1}>
                      <Typography variant="body2" fontWeight={680} noWrap>{worker.device_name}</Typography>
                      <Typography variant="caption" color="text.secondary" noWrap display="block">{worker.node} · {worker.os_name} · {worker.logical_cpu_cores} cores</Typography>
                    </Box>
                    <Stack direction="row" gap={0.7} flexWrap="wrap" justifyContent="flex-end">
                      <Chip size="small" variant="outlined" label={`${worker.completed_tasks} completed`} color={worker.completed_tasks ? 'success' : 'default'} />
                      <Chip size="small" variant="outlined" label={`${worker.claimed_attempts} claimed`} />
                      {worker.active_tasks > 0 && <Chip size="small" variant="outlined" label={`${worker.active_tasks} active`} color="primary" />}
                      {worker.failed_attempts > 0 && <Chip size="small" variant="outlined" label={`${worker.failed_attempts} failed`} color="error" />}
                    </Stack>
                  </Box>
                ))}
              </Box>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </Fragment>
  )
}

function JobTable({ jobs, now }: { jobs: Job[]; now: number }) {
  if (!jobs.length) return <EmptyState icon={Boxes} title="No jobs yet" description="Submit a compute job to split it into chunks and distribute it across connected workers." />
  return (
    <TableContainer>
      <Table sx={{ minWidth: 980 }}>
        <TableHead>
          <TableRow>
            <TableCell>Job</TableCell><TableCell>Status</TableCell><TableCell>Range</TableCell>
            <TableCell sx={{ minWidth: 190 }}>Progress</TableCell><TableCell>Workers</TableCell><TableCell>Duration</TableCell><TableCell>Result</TableCell><TableCell>Created</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {jobs.map((job) => <JobRow key={job.job_id} job={job} now={now} />)}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

function ConnectScreen({
  onConnect, colorMode, onToggleColorMode,
}: {
  onConnect: (url: string, token: string) => Promise<void>
  colorMode: AppColorMode
  onToggleColorMode: () => void
}) {
  const [url, setUrl] = useState(localStorage.getItem(urlKey) ?? import.meta.env.VITE_API_URL ?? '')
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try { await onConnect(url, token) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Connection failed') } finally { setLoading(false) }
  }

  return (
    <Box minHeight="100vh" display="grid" sx={{ placeItems: 'center', p: 2 }}>
      <Tooltip title={`Use ${colorMode === 'dark' ? 'light' : 'dark'} theme`}>
        <IconButton onClick={onToggleColorMode} sx={{ position: 'fixed', right: 20, top: 20, border: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
          {colorMode === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
        </IconButton>
      </Tooltip>
      <Card sx={{ width: '100%', maxWidth: 460, overflow: 'visible', position: 'relative' }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Avatar variant="rounded" sx={{ width: 48, height: 48, bgcolor: 'action.hover', color: 'primary.main', mb: 2.5 }}><Network size={24} /></Avatar>
          <Typography variant="h4">Compute Grid</Typography>
          <Typography color="text.secondary" mt={1} mb={3}>Connect to your coordinator to monitor workers, submit jobs, and follow task progress.</Typography>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Box component="form" onSubmit={submit}>
            <Stack gap={2}>
              <TextField label="Coordinator URL" placeholder="http://192.168.1.20:8000" value={url} onChange={(e) => setUrl(e.target.value)} helperText="Leave blank when using the Vite development proxy" />
              <TextField required label="API token" type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} />
              <Button type="submit" variant="contained" size="large" disabled={loading || !token} startIcon={loading ? <CircularProgress size={18} /> : <Network size={18} />}>Connect to coordinator</Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary" display="block" textAlign="center" mt={2.5}>The token is kept in this browser tab only.</Typography>
        </CardContent>
      </Card>
    </Box>
  )
}

function NewJobDialog({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (job: NewJob) => Promise<void> }) {
  const [jobType, setJobType] = useState<JobType>('prime_count')
  const [start, setStart] = useState('0')
  const [end, setEnd] = useState('1000000')
  const [chunkSize, setChunkSize] = useState('10000')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const job = { job_type: jobType, start: Number(start), end: Number(end), chunk_size: Number(chunkSize) }
    if (![job.start, job.end, job.chunk_size].every(Number.isSafeInteger) || job.end <= job.start || job.chunk_size <= 0) {
      setError('Use safe integers, with end greater than start and a positive chunk size.')
      return
    }
    setLoading(true); setError('')
    try { await onSubmit(job); onClose() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create job') } finally { setLoading(false) }
  }

  return (
    <Dialog open={open} onClose={loading ? undefined : onClose} fullWidth maxWidth="sm">
      <Box component="form" onSubmit={submit}>
        <DialogTitle>Submit compute job</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2.5}>The coordinator will split this half-open range into chunks for idle workers.</Typography>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Stack gap={2}>
            <FormControl fullWidth>
              <InputLabel>Workload</InputLabel>
              <Select value={jobType} label="Workload" onChange={(event) => setJobType(event.target.value as JobType)}>
                <MenuItem value="prime_count">Prime counting</MenuItem>
                <MenuItem value="sum_squares">Sum of squares</MenuItem>
              </Select>
            </FormControl>
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
              <TextField fullWidth required label="Range start" type="number" value={start} onChange={(e) => setStart(e.target.value)} />
              <TextField fullWidth required label="Range end" type="number" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Stack>
            <TextField required label="Chunk size" type="number" value={chunkSize} onChange={(e) => setChunkSize(e.target.value)} helperText={`About ${Math.max(0, Math.ceil((Number(end) - Number(start)) / Number(chunkSize)) || 0).toLocaleString()} tasks`} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 3, pt: 1 }}>
          <Button onClick={onClose} disabled={loading}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={loading} startIcon={loading ? <CircularProgress size={17} /> : <Plus size={17} />}>Create job</Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}

export default function App({
  colorMode, onToggleColorMode,
}: {
  colorMode: AppColorMode
  onToggleColorMode: () => void
}) {
  const theme = useTheme()
  const desktop = useMediaQuery(theme.breakpoints.up('md'))
  const [token, setToken] = useState(sessionStorage.getItem(tokenKey) ?? '')
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem(urlKey) ?? import.meta.env.VITE_API_URL ?? '')
  const [view, setView] = useState<View>('overview')
  const [workers, setWorkers] = useState<Worker[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(Boolean(token))
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [newJobOpen, setNewJobOpen] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const refresh = useCallback(async (silent = false, connection = { baseUrl, token }) => {
    if (!connection.token) return
    if (!silent) setRefreshing(true)
    try {
      const data = await loadDashboard(connection.baseUrl, connection.token)
      setWorkers(data.workers.sort((a, b) => Number(b.online) - Number(a.online)))
      setJobs(data.jobs.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)))
      setLastUpdated(new Date()); setError('')
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Unable to load dashboard'
      setError(message)
      if (reason instanceof ApiError && reason.status === 401) {
        sessionStorage.removeItem(tokenKey); setToken('')
      }
      throw reason
    } finally { setLoading(false); setRefreshing(false) }
  }, [baseUrl, token])

  useEffect(() => {
    if (!token) return
    refresh(true).catch(() => undefined)
    const interval = window.setInterval(() => refresh(true).catch(() => undefined), 3000)
    return () => window.clearInterval(interval)
  }, [refresh, token])

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [])

  async function connect(url: string, nextToken: string) {
    const normalizedUrl = url.trim().replace(/\/$/, '')
    await refresh(false, { baseUrl: normalizedUrl, token: nextToken })
    localStorage.setItem(urlKey, normalizedUrl); sessionStorage.setItem(tokenKey, nextToken)
    setBaseUrl(normalizedUrl); setToken(nextToken)
  }

  function disconnect() {
    sessionStorage.removeItem(tokenKey); setToken(''); setWorkers([]); setJobs([]); setError('')
  }

  async function submitJob(job: NewJob) {
    await createJob(baseUrl, token, job)
    await refresh(false)
    setView('jobs')
  }

  const stats = useMemo(() => {
    const activeWorkers = workers.filter((worker) => worker.online).length
    const runningJobs = jobs.filter((job) => job.status === 'running' || job.status === 'pending').length
    const completedTasks = jobs.reduce((sum, job) => sum + job.completed_tasks, 0)
    const totalCores = workers.filter((worker) => worker.online).reduce((sum, worker) => sum + worker.logical_cpu_cores, 0)
    return { activeWorkers, runningJobs, completedTasks, totalCores }
  }, [jobs, workers])

  if (!token) return <ConnectScreen onConnect={connect} colorMode={colorMode} onToggleColorMode={onToggleColorMode} />

  const drawer = (
    <Box height="100%" display="flex" flexDirection="column">
      <Stack direction="row" alignItems="center" gap={1.3} px={2.5} height={72}>
        <Avatar variant="rounded" sx={{ bgcolor: 'action.hover', color: 'primary.main', width: 38, height: 38 }}><Network size={20} /></Avatar>
        <Box><Typography fontWeight={800} lineHeight={1.1}>Compute Grid</Typography><Typography variant="caption" color="text.secondary">Coordinator</Typography></Box>
      </Stack>
      <Divider />
      <Stack px={1.5} py={2} gap={0.7}>
        {navItems.map((item) => (
          <Button key={item.id} startIcon={<item.icon size={18} />} onClick={() => { setView(item.id); setMobileOpen(false) }} sx={{ justifyContent: 'flex-start', px: 1.5, py: 1.1, color: view === item.id ? 'primary.main' : 'text.secondary', bgcolor: view === item.id ? alpha(theme.palette.primary.main, 0.09) : 'transparent', '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.07) } }}>{item.label}</Button>
        ))}
      </Stack>
      <Box mt="auto" p={2}>
        <Card variant="outlined" sx={{ boxShadow: 'none', bgcolor: alpha(theme.palette.success.main, 0.035) }}>
          <CardContent sx={{ p: 1.6, '&:last-child': { pb: 1.6 } }}>
            <Stack direction="row" alignItems="center" gap={1}><Box width={7} height={7} borderRadius="50%" bgcolor="success.main" /><Typography variant="caption" fontWeight={650}>Coordinator connected</Typography></Stack>
            <Typography variant="caption" color="text.secondary" noWrap display="block" mt={0.6}>{baseUrl || 'Development proxy'}</Typography>
          </CardContent>
        </Card>
      </Box>
    </Box>
  )

  return (
    <Box display="flex" minHeight="100vh">
      <AppBar position="fixed" elevation={0} sx={{ width: { md: `calc(100% - ${drawerWidth}px)` }, ml: { md: `${drawerWidth}px` }, bgcolor: alpha(theme.palette.background.default, 0.94), color: 'text.primary', backdropFilter: 'blur(16px)', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar sx={{ minHeight: '72px !important', px: { xs: 2, sm: 3 } }}>
          {!desktop && <IconButton edge="start" onClick={() => setMobileOpen(true)} sx={{ mr: 1 }}><Menu size={21} /></IconButton>}
          <Box flex={1} minWidth={0}>
            <Typography variant="h6" textTransform="capitalize">{view}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: { xs: 'none', sm: 'block' } }}>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Connecting…'}</Typography>
          </Box>
          <Stack direction="row" gap={1}>
            <Tooltip title={`Use ${colorMode === 'dark' ? 'light' : 'dark'} theme`}>
              <IconButton onClick={onToggleColorMode}>{colorMode === 'dark' ? <Sun size={19} /> : <Moon size={19} />}</IconButton>
            </Tooltip>
            <Tooltip title="Refresh"><span><IconButton onClick={() => refresh(false).catch(() => undefined)} disabled={refreshing}><RefreshCw size={19} className={refreshing ? 'spin' : undefined} /></IconButton></span></Tooltip>
            <Button variant="contained" startIcon={<Plus size={17} />} onClick={() => setNewJobOpen(true)} sx={{ display: { xs: 'none', sm: 'inline-flex' } }}>New job</Button>
            <Tooltip title="Disconnect"><IconButton onClick={disconnect}><LogOut size={19} /></IconButton></Tooltip>
          </Stack>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}>
        <Drawer variant={desktop ? 'permanent' : 'temporary'} open={desktop || mobileOpen} onClose={() => setMobileOpen(false)} ModalProps={{ keepMounted: true }} sx={{ '& .MuiDrawer-paper': { width: drawerWidth, bgcolor: colorMode === 'dark' ? '#0F1928' : '#FFFFFF', borderRightColor: 'divider' } }}>{drawer}</Drawer>
      </Box>

      <Box component="main" flex={1} minWidth={0} sx={{ pt: '72px' }}>
        <Box sx={{ p: { xs: 2, sm: 3, lg: 4 }, maxWidth: 1500, mx: 'auto' }}>
          {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}
          {loading ? (
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', xl: 'repeat(4, 1fr)' }, gap: 2 }}>{[1, 2, 3, 4].map((item) => <Skeleton key={item} variant="rounded" height={150} />)}</Box>
          ) : (
            <>
              {view === 'overview' && (
                <Stack gap={3}>
                  <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', xl: 'repeat(4, 1fr)' }, gap: 2 }}>
                    <StatCard label="Online workers" value={`${stats.activeWorkers}`} detail={`${workers.length} registered devices`} icon={Server} />
                    <StatCard label="Active jobs" value={`${stats.runningJobs}`} detail={`${jobs.length} total submissions`} icon={Activity} />
                    <StatCard label="Completed tasks" value={formatCompact(stats.completedTasks)} detail="Across all in-memory jobs" icon={CheckCircle2} />
                    <StatCard label="Compute capacity" value={`${stats.totalCores}`} detail="Logical cores currently online" icon={Cpu} />
                  </Box>
                  <Card><CardContent sx={{ p: { xs: 2, sm: 3 } }}><SectionTitle title="Recent jobs" description="Live progress from the coordinator queue" action={<Button size="small" onClick={() => setView('jobs')}>View all</Button>} /><JobTable jobs={jobs.slice(0, 6)} now={now} /></CardContent></Card>
                  <Card><CardContent sx={{ p: { xs: 2, sm: 3 } }}><SectionTitle title="Worker fleet" description="Connected devices and current resource snapshots" action={<Button size="small" onClick={() => setView('workers')}>View all</Button>} /><WorkerList workers={workers.slice(0, 4)} /></CardContent></Card>
                </Stack>
              )}
              {view === 'workers' && <Card><CardContent sx={{ p: { xs: 2, sm: 3 } }}><SectionTitle title="Worker fleet" description="Registration details, live resources, and task assignments" /><WorkerList workers={workers} /></CardContent></Card>}
              {view === 'jobs' && <Card><CardContent sx={{ p: { xs: 2, sm: 3 } }}><SectionTitle title="Compute jobs" description="All jobs currently held in coordinator memory" action={<Button variant="contained" startIcon={<Plus size={17} />} onClick={() => setNewJobOpen(true)}>New job</Button>} /><JobTable jobs={jobs} now={now} /></CardContent></Card>}
            </>
          )}
        </Box>
      </Box>
      <Tooltip title="New job"><IconButton onClick={() => setNewJobOpen(true)} sx={{ display: { sm: 'none' }, position: 'fixed', right: 20, bottom: 20, bgcolor: 'primary.main', color: 'primary.contrastText', '&:hover': { bgcolor: 'primary.light' }, boxShadow: 6 }}><Plus /></IconButton></Tooltip>
      <NewJobDialog open={newJobOpen} onClose={() => setNewJobOpen(false)} onSubmit={submitJob} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } .spin { animation: spin .8s linear infinite; }`}</style>
    </Box>
  )
}
