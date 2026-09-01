# Distributed Compute POC

A small distributed compute system for laptops and Android phones. A FastAPI coordinator splits integer ranges into tasks, Python workers pull tasks over HTTP, and the coordinator combines their partial results. All coordinator state is intentionally in memory.

Supported jobs:

- `sum_squares`: sum `n²` over a half-open range `[start, end)`.
- `prime_count`: count primes in `[start, end)`.

Workers execute only these predefined operations; the coordinator cannot send arbitrary Python code.

## Install

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[desktop,dev]'
```

Start the coordinator. Use a strong token and keep it the same on every device:

```bash
export DISTRIBUTED_COMPUTE_TOKEN='replace-with-a-long-random-token'
compute-coordinator --host 0.0.0.0 --port 8000
```

Start one or more workers in other terminals or on other devices. Replace the URL with the coordinator laptop's LAN IP when connecting remotely:

```bash
export DISTRIBUTED_COMPUTE_TOKEN='replace-with-a-long-random-token'
compute-worker --coordinator http://192.168.1.20:8000 --name laptop-1
```

The first worker launch runs a short CPU benchmark and writes its UUID and result to `~/.distributed-compute/worker-state.json`. Later launches reuse both. Delete that file only when you intentionally want a new worker identity and benchmark.

## Android / Termux

Install [Termux](https://termux.dev/) from F-Droid, then install Python and Git. Do not install the `desktop` extra on Android: the worker uses `/proc` and standard Python APIs there instead of `psutil`.

```bash
pkg update
pkg install python git
git clone <this-repository-url>
cd distributed-compute-poc
python -m pip install .
export DISTRIBUTED_COMPUTE_TOKEN='replace-with-a-long-random-token'
compute-worker --coordinator http://192.168.1.20:8000 --name android-phone
```

The phone and coordinator must be able to reach each other. Allow TCP port 8000 through the coordinator machine's firewall, avoid guest Wi-Fi client isolation, and do not expose this HTTP-only POC directly to the internet.

On desktop worker machines, install the `desktop` extra to use `psutil` for resource reporting:

```bash
python -m pip install '.[desktop]'
```

## Submit and inspect jobs

Set shell helpers on the machine making API requests:

```bash
export COORDINATOR_URL='http://127.0.0.1:8000'
export DISTRIBUTED_COMPUTE_TOKEN='replace-with-a-long-random-token'
```

Submit sum of squares for integers 1 through 1,000,000:

```bash
curl -sS -X POST "$COORDINATOR_URL/api/v1/jobs" \
  -H "Authorization: Bearer $DISTRIBUTED_COMPUTE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"job_type":"sum_squares","start":1,"end":1000001,"chunk_size":25000}'
```

Submit a prime-counting job:

```bash
curl -sS -X POST "$COORDINATOR_URL/api/v1/jobs" \
  -H "Authorization: Bearer $DISTRIBUTED_COMPUTE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"job_type":"prime_count","start":0,"end":1000000,"chunk_size":10000}'
```

Use the returned job ID to inspect progress and the final result:

```bash
curl -sS "$COORDINATOR_URL/api/v1/jobs/JOB_ID" \
  -H "Authorization: Bearer $DISTRIBUTED_COMPUTE_TOKEN"

curl -sS "$COORDINATOR_URL/api/v1/workers" \
  -H "Authorization: Bearer $DISTRIBUTED_COMPUTE_TOKEN"
```

Interactive API documentation is available at `http://COORDINATOR_HOST:8000/docs`.

## Behavior and limitations

- Workers send their device name, hostname/node, OS, logical CPU count, available RAM, current CPU utilization, and persisted benchmark during registration. CPU and RAM data are refreshed on every task poll. Desktop installs use `psutil`; Android/Termux uses `/proc/stat`, `/proc/meminfo`, and standard Python APIs.
- Tasks use fixed-size chunks. Faster workers naturally claim more chunks instead of receiving specially sized tasks.
- A claim has a 30-second lease. Workers renew it with background heartbeats during long computations. An abandoned task is requeued and is permanently failed after three unsuccessful leases or reported failures.
- The worker reconnects with exponential backoff after network failures.
- Run exactly one coordinator process. Multiple Uvicorn workers would each have a separate queue.
- Coordinator restarts erase worker records, jobs, task progress, and results. Workers automatically register again.
- Authentication uses one shared bearer token. Traffic is not encrypted, so use this only on a trusted/firewalled LAN or place it behind HTTPS/VPN.

## Test

```bash
pytest
```
