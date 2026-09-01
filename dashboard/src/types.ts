export type JobType = 'sum_squares' | 'prime_count'
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface Benchmark {
  elapsed_seconds: number
  operations: number
  operations_per_second: number
}

export interface Worker {
  worker_id: string
  device_name: string
  node: string
  os_name: string
  os_release: string
  logical_cpu_cores: number
  available_ram_bytes: number
  cpu_usage_percent: number
  benchmark: Benchmark
  registered_at: string
  last_seen: string
  online: boolean
  current_task_id: string | null
}

export interface JobWorkerContribution {
  worker_id: string
  device_name: string
  node: string
  os_name: string
  logical_cpu_cores: number
  claimed_attempts: number
  completed_tasks: number
  active_tasks: number
  failed_attempts: number
}

export interface Job {
  job_id: string
  job_type: JobType
  start: number
  end: number
  chunk_size: number
  status: JobStatus
  created_at: string
  started_at: string | null
  completed_at: string | null
  total_tasks: number
  pending_tasks: number
  leased_tasks: number
  completed_tasks: number
  failed_tasks: number
  worker_count: number
  workers: JobWorkerContribution[]
  result: number | null
  error: string | null
}

export interface NewJob {
  job_type: JobType
  start: number
  end: number
  chunk_size: number
}
