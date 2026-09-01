import type { Job, NewJob, Worker } from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/$/, '')
}

async function request<T>(
  baseUrl: string,
  token: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

export async function loadDashboard(baseUrl: string, token: string) {
  const [workers, jobs] = await Promise.all([
    request<Worker[]>(baseUrl, token, '/api/v1/workers'),
    request<Job[]>(baseUrl, token, '/api/v1/jobs'),
  ])
  return { workers, jobs }
}

export function createJob(baseUrl: string, token: string, job: NewJob) {
  return request<Job>(baseUrl, token, '/api/v1/jobs', {
    method: 'POST',
    body: JSON.stringify(job),
  })
}
