# StorageWatch
## Product Requirements Plan

### 1. Project Overview

StorageWatch is a macOS filesystem observability platform designed for organizations running private or local AI infrastructure. Its purpose is to help system administrators understand the health, capacity, and performance of storage systems used by AI workloads.

Private AI systems can process very large datasets stored on local disks or shared network volumes. These workloads may continuously read model files, vector databases, documents, datasets, checkpoints, logs, and generated outputs. If storage performance becomes slow or a filesystem approaches its capacity limit, the AI system can experience major performance problems.

StorageWatch provides administrators with a centralized dashboard where they can monitor filesystem health and investigate abnormal storage activity.

The minimum viable product will focus on a single macOS machine using APFS. A lightweight Python monitoring agent will collect filesystem telemetry from the Mac and send that information to a cloud-hosted backend. The backend will store historical measurements in Tiger Data and expose them through a FastAPI API. A React dashboard will visualize the information, Auth0 will protect administrator access, Backboard will provide AI-generated explanations of detected anomalies, Vultr will host the application, and a sponsored .tech domain will provide a public URL.

---

# 2. Problem Statement

Organizations running AI workloads locally need reliable storage infrastructure.

AI applications may interact with extremely large amounts of data, including:

- training datasets
- retrieval-augmented generation documents
- embeddings
- vector databases
- model checkpoints
- application logs
- user files
- generated content
- research datasets

Storage problems can therefore directly affect AI performance.

Administrators need to answer questions such as:

- How much storage is currently being used?
- How much storage remains?
- Is the filesystem approaching capacity?
- How fast is the system reading data?
- How fast is the system writing data?
- Has disk activity suddenly increased?
- Is current activity significantly different from normal behavior?
- What may be causing an unusual spike?
- What should an administrator investigate?

On macOS, administrators may need to use multiple command-line tools and manually interpret the results.

StorageWatch combines these measurements into one monitoring platform.

---

# 3. Product Goal

The primary goal of StorageWatch is to provide administrators with a simple and understandable interface for monitoring macOS storage systems supporting private AI infrastructure.

The system should provide:

1. Real-time filesystem information.
2. Historical storage telemetry.
3. Storage capacity monitoring.
4. Read and write performance monitoring.
5. Basic anomaly detection.
6. Administrator alerts.
7. AI-assisted explanations of abnormal activity.
8. Secure administrator authentication.
9. Remote dashboard access.

The goal is not to replace enterprise storage monitoring platforms.

The hackathon version should demonstrate that a lightweight, macOS-focused monitoring architecture can provide useful visibility into AI storage infrastructure.

---

# 4. Target Users

The primary user is a system administrator responsible for machines running local AI workloads.

Potential users include:

- AI infrastructure administrators
- university research laboratories
- healthcare organizations
- law firms
- small businesses running private AI
- machine learning engineers
- DevOps engineers
- research computing teams
- organizations using Mac Studios or Apple Silicon systems for AI workloads

The MVP assumes one administrator monitoring one Mac.

Future versions may support multiple machines and multiple administrators.

---

# 5. Core User Story

As a system administrator,

I want to monitor the filesystem used by my local AI infrastructure,

so that I can quickly understand storage capacity, filesystem performance, and abnormal activity before those issues affect AI workloads.

---

# 6. Secondary User Stories

### Storage Capacity

As an administrator, I want to know how much disk space is being used so that I can prevent the filesystem from becoming full.

### Performance

As an administrator, I want to see current disk read and write throughput so that I can identify possible storage bottlenecks.

### Historical Monitoring

As an administrator, I want to see previous filesystem activity so that I can compare current behavior with past behavior.

### Anomaly Detection

As an administrator, I want the system to detect unusual write activity so that I do not need to manually monitor the dashboard continuously.

### AI Assistance

As an administrator, I want an AI assistant to explain unusual storage behavior so that I can understand possible causes without manually analyzing every metric.

### Authentication

As an administrator, I want the monitoring dashboard protected by authentication so that unauthorized users cannot view infrastructure information.

---

# 7. System Architecture

The system should follow this architecture:

Mac Computer  
↓  
Python Monitoring Agent  
↓  
HTTPS POST Request  
↓  
FastAPI Backend on Vultr  
↓  
Tiger Data Database  
↓  
React Dashboard  
↓  
Authenticated Administrator

Additional services:

Auth0 → administrator authentication

Backboard → AI analysis

.tech → public application domain

The Mac monitoring agent must push telemetry to the backend.

The backend should not attempt to remotely inspect the filesystem because the monitored filesystem exists on the administrator's Mac.

---

# 8. High-Level Architecture

```text
┌─────────────────────────────────────┐
│             macOS Host              │
│                                     │
│ Python Monitoring Agent             │
│                                     │
│ • APFS detection                    │
│ • capacity monitoring               │
│ • read throughput                   │
│ • write throughput                  │
│ • hostname                          │
└────────────────┬────────────────────┘
                 │
                 │ HTTPS / JSON
                 │ POST /api/metrics
                 ▼
┌─────────────────────────────────────┐
│            Vultr Server             │
│                                     │
│ FastAPI Backend                     │
│                                     │
│ • telemetry ingestion               │
│ • database queries                  │
│ • alert detection                   │
│ • AI integration                    │
└───────────┬───────────────────┬─────┘
            │                   │
            ▼                   ▼
┌──────────────────┐      ┌──────────────┐
│   Tiger Data     │      │  Backboard   │
│                  │      │              │
│ Time-series DB   │      │ AI analysis  │
└──────────┬───────┘      └──────┬───────┘
           │                      │
           └──────────┬───────────┘
                      ▼
             ┌─────────────────┐
             │ React Dashboard │
             │                 │
             │ Auth0 Protected │
             └────────┬────────┘
                      │
                      ▼
              storagewatch.tech
```

---

# 9. Technology Stack

## macOS Agent

Language:

Python

Libraries:

- psutil
- requests
- subprocess
- platform
- datetime

Purpose:

Collect filesystem and disk metrics from macOS.

---

## Backend

Framework:

FastAPI

Language:

Python

Libraries:

- FastAPI
- Pydantic
- psycopg2
- python-dotenv
- Backboard SDK
- Uvicorn/Gunicorn

Purpose:

- receive telemetry
- validate telemetry
- write telemetry to Tiger Data
- retrieve historical metrics
- detect anomalies
- generate alerts
- communicate with Backboard

---

## Database

Platform:

Tiger Data / TimescaleDB

Purpose:

Store time-series filesystem telemetry.

Why Tiger Data:

Filesystem monitoring naturally produces timestamped measurements.

Example:

12:00:00 → 75 MB/s

12:00:05 → 120 MB/s

12:00:10 → 950 MB/s

12:00:15 → 1.1 GB/s

This is ideal time-series data.

---

## Frontend

Framework:

React

Build tool:

Vite

Libraries:

- Axios
- Recharts
- Auth0 React SDK

Purpose:

Display infrastructure information in an understandable dashboard.

---

## Authentication

Provider:

Auth0

Purpose:

Protect infrastructure telemetry from unauthorized users.

---

## AI Analysis

Provider:

Backboard

Purpose:

Explain detected anomalies.

Backboard should not operate as a general-purpose chatbot.

The AI should receive actual infrastructure telemetry and produce short technical explanations.

---

## Hosting

Provider:

Vultr

Purpose:

Host:

- FastAPI backend
- React frontend
- Nginx reverse proxy

---

## Domain

Provider:

.tech

Example:

storagewatch.tech

Purpose:

Provide a clean public URL for the hackathon demo.

---

# 10. macOS Monitoring Agent

The monitoring agent is one of the most important components.

It runs directly on the monitored Mac.

The agent should collect metrics approximately every five seconds.

Example telemetry:

```json
{
    "timestamp": "2026-09-12T17:30:15Z",
    "hostname": "Shrutis-MacBook-Pro",
    "filesystem": "/",
    "filesystem_type": "APFS",
    "total_bytes": 494384795648,
    "used_bytes": 301238293504,
    "free_bytes": 193146502144,
    "used_percent": 61.4,
    "read_bytes_per_sec": 1740800,
    "write_bytes_per_sec": 532480
}
```

The agent then sends:

POST /api/metrics

to the Vultr backend.

---

# 11. Filesystem Capacity Collection

Python should use:

```python
psutil.disk_usage("/")
```

Expected information:

```text
total
used
free
percent
```

These values populate:

- total_bytes
- used_bytes
- free_bytes
- used_percent

---

# 12. APFS Detection

The application should detect the local filesystem type.

macOS command:

```bash
diskutil info /
```

The Python application can execute this using subprocess.

The program should locate:

```text
File System Personality: APFS
```

and return:

```json
"filesystem_type": "APFS"
```

---

# 13. I/O Performance Monitoring

Use:

```python
psutil.disk_io_counters()
```

The agent should sample disk counters at two different times.

Example:

Sample 1:

```text
read_bytes = 10,000,000
write_bytes = 5,000,000
```

One second later:

```text
read_bytes = 15,000,000
write_bytes = 8,000,000
```

Calculate:

```text
read throughput =
15,000,000 - 10,000,000
= 5,000,000 bytes/sec
```

Write throughput:

```text
8,000,000 - 5,000,000
= 3,000,000 bytes/sec
```

These values are sent to the backend.

---

# 14. Database Schema

Primary table:

```sql
CREATE TABLE filesystem_metrics (
    time TIMESTAMPTZ NOT NULL,
    hostname TEXT NOT NULL,
    filesystem TEXT NOT NULL,
    filesystem_type TEXT,

    total_bytes BIGINT,
    used_bytes BIGINT,
    free_bytes BIGINT,

    used_percent DOUBLE PRECISION,

    read_bytes_per_sec BIGINT,
    write_bytes_per_sec BIGINT
);
```

Tiger Data can convert this into a hypertable:

```sql
SELECT create_hypertable(
    'filesystem_metrics',
    'time'
);
```

---

# 15. Alerts Schema

Optional but recommended:

```sql
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    hostname TEXT,

    alert_type TEXT,

    severity TEXT,

    message TEXT,

    metric_value DOUBLE PRECISION,

    resolved BOOLEAN DEFAULT FALSE
);
```

Example alert:

```text
id: 21

alert_type:
HIGH_WRITE_ACTIVITY

severity:
warning

message:
Write throughput exceeded recent baseline.

metric_value:
821000000
```

---

# 16. Backend API

The backend should expose the following endpoints.

## POST /api/metrics

Purpose:

Receive telemetry from the Mac agent.

Example:

```json
{
    "hostname": "MacBook-Pro",
    "used_percent": 65.2,
    "read_bytes_per_sec": 150000000,
    "write_bytes_per_sec": 420000000
}
```

Backend actions:

1. Validate payload.
2. Save telemetry.
3. Run anomaly rules.
4. Create alert if required.
5. Return success.

---

## GET /api/metrics/current

Purpose:

Return the most recent telemetry record.

Used by dashboard metric cards.

---

## GET /api/metrics/history

Purpose:

Return historical telemetry.

Example:

Last 100 records.

Used by Recharts.

---

## GET /api/alerts

Purpose:

Return recent alerts.

---

## POST /api/ai/explain

Purpose:

Send current anomaly information to Backboard.

Returns AI explanation.

---

# 17. Pydantic Metrics Model

Example:

```python
class Metrics(BaseModel):

    timestamp: str

    hostname: str

    filesystem: str

    filesystem_type: str

    total_bytes: int

    used_bytes: int

    free_bytes: int

    used_percent: float

    read_bytes_per_sec: int

    write_bytes_per_sec: int
```

This prevents malformed telemetry from entering the database.

---

# 18. Capacity Alert Logic

Basic thresholds:

Healthy:

```text
0-79%
```

Warning:

```text
80-89%
```

Critical:

```text
90-100%
```

Example implementation:

```python
if used_percent >= 90:
    severity = "critical"

elif used_percent >= 80:
    severity = "warning"

else:
    severity = "healthy"
```

---

# 19. I/O Anomaly Detection

For the MVP, anomaly detection should be simple and explainable.

One method:

Calculate the average write speed of the previous twenty samples.

Example:

```text
baseline write speed:
100 MB/s

current write speed:
720 MB/s
```

Calculate:

```text
720 / 100 = 7.2x baseline
```

Trigger warning when:

```python
current_write > baseline * 4
```

This should be described as:

"baseline-based anomaly detection."

Do not describe it as machine learning.

---

# 20. Backboard AI Analysis

Backboard should receive structured telemetry.

Example prompt:

```text
You are an infrastructure monitoring assistant.

Analyze this macOS filesystem event.

Filesystem:
APFS

Storage utilization:
82%

Current read throughput:
115 MB/s

Current write throughput:
820 MB/s

Average write throughput:
105 MB/s

Detected anomaly:
Current write activity is approximately 7.8 times
higher than the recent baseline.

Explain:

1. What happened.
2. Possible causes.
3. Severity.
4. What the administrator should inspect.

Keep the response concise and technical.
```

Possible response:

```text
The APFS volume is experiencing a significant
increase in write activity.

Current write throughput is approximately 7.8x
the recent baseline.

Possible causes include a dataset import,
model checkpoint creation, backup operation,
large file transfer, or unexpected process.

The filesystem is also above 80% capacity,
increasing the importance of monitoring continued
growth.

Inspect active disk-intensive processes and
recently modified directories.
```

---

# 21. Dashboard Requirements

The dashboard should be a single page.

Do not create unnecessary pages.

Recommended layout:

```text
--------------------------------------------------
StorageWatch                      SYSTEM HEALTHY

MacBook-Pro                       Admin
--------------------------------------------------

STORAGE        READ             WRITE

62%            240 MB/s         95 MB/s

████████████░░░░░

--------------------------------------------------

I/O PERFORMANCE

      /\        /\
_____/  \______/  \_____

--------------------------------------------------

ALERTS                  AI ANALYSIS

High Write Activity     Current write activity
                        is 6.8x above baseline...

[Explain with AI]

--------------------------------------------------
```

---

# 22. Dashboard Components

## System Status

Values:

- Healthy
- Warning
- Critical

---

## Storage Card

Display:

- filesystem
- filesystem type
- storage percentage
- used GB
- available GB
- total GB

---

## Performance Cards

Display:

Read throughput:

```text
242 MB/s
```

Write throughput:

```text
96 MB/s
```

---

## Performance Graph

Display two lines:

- read throughput
- write throughput

Time on X-axis.

Throughput on Y-axis.

---

## Alerts Panel

Example:

```text
WARNING

High write activity detected.

Current:
812 MB/s

Baseline:
102 MB/s
```

---

## AI Analysis Panel

Button:

```text
Explain with AI
```

After clicking:

Display Backboard response.

---

# 23. Authentication

Auth0 should protect the dashboard.

Flow:

```text
visitor
↓
storagewatch.tech
↓
not authenticated
↓
Auth0 login
↓
authenticated
↓
dashboard
```

For the MVP:

One administrator role is sufficient.

Advanced RBAC is unnecessary.

---

# 24. Security Considerations

Secrets should never be committed to GitHub.

Store the following in environment variables:

```text
TIGER_DATABASE_URL

BACKBOARD_API_KEY

AUTH0_DOMAIN

AUTH0_CLIENT_ID
```

Gitignore:

```text
.env

venv/

node_modules/

__pycache__/

dist/
```

HTTPS should be used in production.

---

# 25. Vultr Deployment

Vultr hosts the web infrastructure.

Recommended deployment:

```text
Vultr Ubuntu VM

Nginx
├── React frontend
└── /api → FastAPI
```

The Python monitoring agent remains on the Mac.

Important:

The Mac must push data to the Vultr server.

Do not run the collector on Vultr when demonstrating Mac metrics because that would monitor the Linux VM instead of the Mac.

---

# 26. Network Flow

```text
Mac Agent

POST
https://storagewatch.tech/api/metrics

↓

Vultr Nginx

↓

FastAPI

↓

Tiger Data
```

Dashboard request:

```text
Browser

GET
/api/metrics/current

↓

FastAPI

↓

Tiger Data

↓

JSON

↓

React Dashboard
```

AI request:

```text
React

POST
/api/ai/explain

↓

FastAPI

↓

recent telemetry

↓

Backboard

↓

AI explanation

↓

dashboard
```

---

# 27. Demo Scenario

The demo should show a real storage event.

Step 1:

Open:

```text
storagewatch.tech
```

Step 2:

Login using Auth0.

Step 3:

Show:

```text
Filesystem: APFS

Usage: 62%

Read: 140 MB/s

Write: 32 MB/s
```

Step 4:

Generate disk activity.

Example:

```bash
mkfile 2g ~/storagewatch-demo
```

Step 5:

Collector detects increased write activity.

Example:

```text
32 MB/s
↓
730 MB/s
```

Step 6:

Tiger Data stores the event.

Step 7:

Dashboard graph spikes.

Step 8:

An alert appears:

```text
HIGH WRITE ACTIVITY

7.1x baseline
```

Step 9:

Click:

```text
Explain with AI
```

Step 10:

Backboard explains what happened.

Step 11:

Delete test file:

```bash
rm ~/storagewatch-demo
```

---

# 28. Expected Demo Story

The team should explain:

"StorageWatch continuously collects filesystem telemetry directly from a macOS machine. The agent sends these measurements to our FastAPI backend hosted on Vultr. We store historical telemetry in Tiger Data because filesystem monitoring is naturally a time-series workload.

Our React dashboard gives administrators real-time storage visibility. Auth0 protects access to sensitive infrastructure information.

When the monitoring system detects activity significantly above the normal baseline, it generates an alert. Administrators can then ask Backboard to explain the anomaly using the actual filesystem telemetry."

---

# 29. MVP Requirements

The project is considered complete when the following features work:

- Detect APFS.
- Display filesystem total capacity.
- Display used storage.
- Display available storage.
- Calculate storage percentage.
- Calculate read throughput.
- Calculate write throughput.
- Push telemetry from Mac to backend.
- Store telemetry in Tiger Data.
- Retrieve historical telemetry.
- Display performance graph.
- Detect high capacity.
- Detect abnormal write activity.
- Display alerts.
- Authenticate administrator through Auth0.
- Send anomaly information to Backboard.
- Display AI explanation.
- Host backend and frontend on Vultr.
- Expose application through .tech domain.
- Maintain public GitHub repository.
- Include build and execution instructions.

---

# 30. Non-Goals for the MVP

Do not spend hackathon development time implementing:

- complex machine learning
- blockchain
- ElevenLabs
- mobile application
- multi-tenant architecture
- complicated RBAC
- NFS/pNFS if time is limited
- automatic remediation
- full process tracing
- distributed monitoring
- advanced storage forecasting

These should be documented as future work.

---

# 31. Future Work

StorageWatch could later support:

### NFS and pNFS

Monitor shared storage used by multiple machines.

### Multiple Macs

Allow one dashboard to monitor many Mac Studios.

Example:

```text
Mac-Studio-01
Mac-Studio-02
Mac-Studio-03
Mac-Studio-04
```

### Per-User Storage Monitoring

Show:

```text
User        Used        Quota

Alice       410 GB      500 GB

Bob         122 GB      500 GB

Carol       488 GB      500 GB
```

### Capacity Forecasting

Use historical growth rate to predict:

```text
Filesystem expected to exceed
90% utilization in approximately 4 days.
```

### Process-Level Attribution

Identify which process is responsible for unusual I/O.

Example:

```text
python3

write throughput:
620 MB/s
```

### Machine Learning

Train anomaly detection models using historical filesystem activity.

### Notifications

Send alerts through:

- email
- Slack
- Microsoft Teams
- PagerDuty

---

# 32. Suggested Repository Structure

```text
storagewatch/

├── collector/
│   ├── __init__.py
│   └── collector.py
│
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── alerts.py
│   └── ai.py
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── MetricCard.jsx
│   │   │   ├── StorageChart.jsx
│   │   │   ├── AlertPanel.jsx
│   │   │   └── AIAnalysis.jsx
│   │   └── main.jsx
│   │
│   └── package.json
│
├── requirements.txt
├── .gitignore
├── README.md
└── LICENSE
```

---

# 33. Development Priority

Build in this order:

### Priority 1

Python macOS collector.

### Priority 2

FastAPI API.

### Priority 3

Basic React dashboard.

### Priority 4

Tiger Data.

### Priority 5

Historical graphs.

### Priority 6

Alerts.

### Priority 7

Backboard.

### Priority 8

Auth0.

### Priority 9

Vultr.

### Priority 10

.tech domain.

### Priority 11

README and presentation.

---

# 34. Success Criteria

The project succeeds if a judge can see the following sequence:

```text
Mac filesystem activity

↓

live monitoring agent

↓

remote telemetry ingestion

↓

historical Tiger Data storage

↓

real-time React visualization

↓

automatic anomaly detection

↓

administrator alert

↓

Backboard diagnosis
```

The entire flow must use real data rather than manually entered dashboard values.

---

# 35. Product Differentiation

StorageWatch differs from a basic disk monitor because it combines:

- macOS-native monitoring
- remote infrastructure telemetry
- time-series storage
- administrator authentication
- historical analysis
- anomaly detection
- AI-assisted diagnosis

The project is specifically positioned around storage infrastructure supporting local and private AI systems.

---

# 36. Final Product Pitch

StorageWatch is a macOS filesystem observability platform built for organizations running private AI infrastructure.

A lightweight local agent continuously monitors APFS storage capacity and disk I/O performance. Telemetry is securely transmitted to a FastAPI backend running on Vultr and stored in Tiger Data for historical analysis.

Administrators access an Auth0-protected React dashboard where they can monitor current storage health, visualize historical performance, and receive alerts when capacity or I/O behavior becomes abnormal.

When an anomaly occurs, StorageWatch uses Backboard to analyze the filesystem telemetry and provide an understandable explanation of what may be happening and what the administrator should investigate.

The result is a lightweight storage observability system designed specifically for the growing ecosystem of local AI infrastructure running on Apple Silicon.