# Resource Monitoring and Analysis Guide

## Overview

This guide explains how our resource monitoring system collects container metrics and analyzes them to provide insights into CPU, memory, and system performance. This is designed for beginners who want to understand container resource monitoring.

## Table of Contents

1. [What is Resource Monitoring?](#what-is-resource-monitoring)
2. [CSV Data Structure](#csv-data-structure)
3. [Input Parameters Explained](#input-parameters-explained)
4. [Calculations and Conversions](#calculations-and-conversions)
5. [Resource Analyzer Script Usage](#resource-analyzer-script-usage)
6. [Output Insights](#output-insights)
7. [Understanding the Visualizations](#understanding-the-visualizations)

---

## What is Resource Monitoring?

Resource monitoring tracks how much CPU, memory, disk, and network resources your containers are using. This helps you:

- **Identify Performance Issues**: Find containers that are using too many resources
- **Optimize Resource Allocation**: Set appropriate limits and requests
- **Prevent System Overload**: Detect when containers are competing for resources
- **Plan Capacity**: Understand resource usage patterns for scaling decisions

---

## CSV Data Structure

The monitoring script (`monitor_resources.sh`) collects metrics every 24 seconds and saves them to a CSV file. Each row represents one monitoring snapshot with 85 columns of data.

### Main Categories of Data:
- **Pod-level information** (6 columns)
- **kubectl metrics** (7 columns) 
- **Runner container metrics** (36 columns)
- **DinD container metrics** (36 columns)

---

## Input Parameters Explained

### 🎯 **Pod-Level Information**

| Parameter | Description | Why It Matters |
|-----------|-------------|----------------|
| `timestamp` | When the measurement was taken | Tracks changes over time |
| `pod_phase` | Pod status (Running, Pending, etc.) | Ensures pod is healthy |
| `container_count` | Total containers in the pod | Verifies expected pod structure |
| `ready_containers` | How many containers are ready | Detects container startup issues |
| `total_restarts` | Number of container restarts | Indicates stability problems |
| `node_name` | Which Kubernetes node hosts the pod | Helps identify node-specific issues |

**💡 Beginner Tip**: If `ready_containers` < `container_count`, some containers are having problems starting.

---

### ⚡ **CPU Metrics (Most Important)**

#### Raw CPU Data from cgroups:
| Parameter | Description | Units | Why It Matters |
|-----------|-------------|-------|----------------|
| `runner_cpu_usage_usec` | **Total CPU time used since container start** | Microseconds | Primary metric for calculating actual CPU usage |
| `runner_cpu_user_usec` | CPU time spent in user space (application code) | Microseconds | Shows how much CPU your application logic uses |
| `runner_cpu_system_usec` | CPU time spent in kernel space (system calls) | Microseconds | Shows system overhead (file I/O, network, etc.) |
| `runner_cpu_nr_periods` | Number of CPU scheduling periods | Count | Used to calculate throttling percentage |
| `runner_cpu_nr_throttled` | How many periods CPU was throttled | Count | Indicates if CPU limits are being hit |
| `runner_cpu_throttled_usec` | Total time spent throttled | Microseconds | Shows impact of CPU limiting |

**🔍 Key Insight**: `cpu_usage_usec` is **cumulative** - it keeps growing. To get actual usage rate, we calculate the difference between measurements.

#### How We Calculate CPU Usage Rate:
```
CPU Rate (millicores) = (Current cpu_usage_usec - Previous cpu_usage_usec) / Time_Interval / 1000

Example:
- Previous reading: 233,395,090 μs
- Current reading:  282,067,624 μs  
- Time interval: 24 seconds
- Delta: 282,067,624 - 233,395,090 = 48,672,534 μs
- Rate: 48,672,534 ÷ 24 ÷ 1000 = 2,028 millicores = 2.03 CPU cores
```

**💡 Understanding CPU Units**:
- **1 CPU core** = 1,000 millicores = 1,000,000 microseconds per second
- **500 millicores** = 0.5 CPU cores = 50% of one CPU core
- **2000 millicores** = 2 CPU cores = 200% CPU usage

---

### 💾 **Memory Metrics**

| Parameter | Description | Units | Why It Matters |
|-----------|-------------|-------|----------------|
| `runner_memory_current` | **Current memory usage** | Bytes | Main metric for memory consumption |
| `runner_memory_max` | Memory limit set for container | Bytes | Shows maximum allowed memory |
| `runner_memory_rss` | Resident Set Size (RAM actually used) | Bytes | Physical memory in use |
| `runner_memory_cache` | Page cache and buffers | Bytes | Memory used for caching files |
| `runner_memory_swap` | Swap memory usage | Bytes | Indicates memory pressure |
| `runner_memory_pgfault` | Minor page faults | Count | Memory access patterns |
| `runner_memory_pgmajfault` | Major page faults (disk reads) | Count | Indicates memory thrashing |

**🔍 Memory Types Explained**:
- **RSS (Resident Set Size)**: Actual RAM your process is using right now
- **Cache**: Memory used to speed up file access (can be freed if needed)
- **Swap**: When RAM is full, less-used memory gets moved to disk
- **Page Faults**: When program accesses memory that isn't loaded in RAM

#### Memory Calculations:
```
Memory Usage (GB) = memory_current ÷ (1024³)
Memory Utilization (%) = (memory_current ÷ memory_max) × 100

Example:
- Current usage: 8,009,613,312 bytes = 7.46 GB
- Memory limit: 8,589,934,592 bytes = 8.00 GB  
- Utilization: 93.2% of limit
```

---

### 🔧 **Process and System Metrics**

| Parameter | Description | Units | Why It Matters |
|-----------|-------------|-------|----------------|
| `runner_pids_current` | Number of running processes | Count | Shows application complexity |
| `runner_pids_max` | Maximum allowed processes | Count | Process limit enforcement |
| `runner_load_1min` | System load average (1 minute) | Ratio | Overall system busy-ness |
| `runner_process_count` | Total processes (including threads) | Count | Detailed process tracking |
| `runner_disk_usage_percent` | Disk space used | Percentage | Storage consumption |
| `runner_disk_available_kb` | Available disk space | Kilobytes | Remaining storage |

**💡 Understanding System Load**:
- **Load = 1.0**: System is fully utilized but not overloaded
- **Load = 2.0**: System is 100% overloaded (twice as much work as it can handle)
- **Load = 0.5**: System is 50% utilized
- **Load > 4.0**: System is severely overloaded

---

### 🌐 **Network Metrics**

| Parameter | Description | Units | Why It Matters |
|-----------|-------------|-------|----------------|
| `runner_network_rx_bytes` | Bytes received (downloaded) | Bytes | Network input traffic |
| `runner_network_tx_bytes` | Bytes transmitted (uploaded) | Bytes | Network output traffic |

---

### 📊 **Pressure Stall Information (PSI)**

| Parameter | Description | Units | Why It Matters |
|-----------|-------------|-------|----------------|
| `runner_cpu_pressure_some_avg10` | % of time waiting for CPU (10s avg) | Percentage | CPU contention indicator |
| `runner_memory_pressure_some_avg10` | % of time waiting for memory (10s avg) | Percentage | Memory pressure indicator |
| `runner_io_pressure_some_avg10` | % of time waiting for I/O (10s avg) | Percentage | Disk/network bottlenecks |

**🔍 PSI Explained**: PSI measures how much time your workload spends waiting for resources:
- **0%**: No waiting, resources are available
- **10%**: Mild resource pressure 
- **50%**: Significant resource bottlenecks
- **90%+**: Severe resource starvation

**⚠️ Note**: PSI is only available in cgroups v2. Our GitHub Actions runners use cgroups v1, so these values are always 0.

---

## Calculations and Conversions

### 1. **CPU Usage Rate Calculation**

The script converts cumulative CPU microseconds to millicores (CPU usage rate):

```python
def convert_cpu_to_millicores(cpu_usage_usec, interval_seconds):
    rates = [0]  # First measurement has no previous reference
    for i in range(1, len(cpu_usage_usec)):
        delta_usec = cpu_usage_usec[i] - cpu_usage_usec[i-1]
        millicores = (delta_usec / interval_seconds) / 1000.0
        rates.append(millicores)
    return rates
```

**Why this works**:
- `delta_usec` = CPU time used during the interval
- `delta_usec / interval_seconds` = microseconds of CPU per second
- Divide by 1000 to convert to millicores (since 1 core = 1,000,000 μs/s)

### 2. **Memory Unit Conversions**

```python
# Convert bytes to megabytes
memory_mb = memory_bytes / (1024 * 1024)

# Convert bytes to gigabytes  
memory_gb = memory_bytes / (1024 * 1024 * 1024)

# Calculate memory utilization percentage
utilization_pct = (current_memory / memory_limit) * 100
```

### 3. **CPU Throttling Rate**

```python
throttling_pct = (nr_throttled / nr_periods) * 100 if nr_periods > 0 else 0
```

This shows what percentage of CPU scheduling periods were throttled due to limits.

---

## Resource Analyzer Script Usage

The `resource_analyzer.py` script processes the CSV data and focuses on a specific subset of metrics to provide meaningful insights. Here's exactly which metrics are used and how they're processed.

### 📊 **Metrics Used by the Analyzer**

Out of the 85 available CSV columns, the analyzer uses **18 key metrics** for calculations and visualizations:

#### **Core Processing Metrics (7 metrics)**
| CSV Column | Purpose in Script | Processing Method |
|------------|-------------------|-------------------|
| `timestamp` | Time-series analysis | Converted to datetime, creates time baseline |
| `runner_cpu_usage_usec` | **Primary CPU calculation** | Delta calculation → millicores conversion |
| `dind_cpu_usage_usec` | **Primary CPU calculation** | Delta calculation → millicores conversion |
| `runner_memory_current` | **Primary memory analysis** | Direct conversion to MB/GB |
| `dind_memory_current` | **Primary memory analysis** | Direct conversion to MB/GB |
| `runner_memory_max` | Memory limit analysis | Converted to GB (handles 'max' values) |
| `dind_memory_max` | Memory limit analysis | Converted to GB (handles 'max' values) |

#### **CPU Throttling Analysis (4 metrics)**
| CSV Column | Purpose in Script | Processing Method |
|------------|-------------------|-------------------|
| `runner_cpu_nr_periods` | CPU throttling calculation | Used in percentage formula |
| `runner_cpu_nr_throttled` | CPU throttling calculation | Used in percentage formula |
| `dind_cpu_nr_periods` | CPU throttling calculation | Used in percentage formula |
| `dind_cpu_nr_throttled` | CPU throttling calculation | Used in percentage formula |

#### **System and Process Metrics (4 metrics)**
| CSV Column | Purpose in Script | Processing Method |
|------------|-------------------|-------------------|
| `runner_pids_current` | Process count visualization | Direct plotting |
| `dind_pids_current` | Process count visualization | Direct plotting |
| `runner_load_1min` | System load analysis | Direct plotting + summary stats |
| `dind_load_1min` | System load analysis | Direct plotting + summary stats |

### 🔄 **Data Processing Pipeline**

The script follows this processing pipeline:

#### **1. Data Loading and Preparation**
```python
# Load CSV file
df = pd.read_csv(csv_file)

# Convert timestamps to datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['time_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60

# Auto-detect monitoring interval
interval_seconds = (df['timestamp'].iloc[1] - df['timestamp'].iloc[0]).total_seconds()
```

#### **2. CPU Usage Rate Calculation**
```python
def convert_cpu_to_millicores(cpu_usage_usec, interval_seconds):
    rates = [0]  # First measurement has no previous reference
    for i in range(1, len(cpu_usage_usec)):
        delta_usec = max(0, cpu_usage_usec[i] - cpu_usage_usec[i-1])
        millicores = (delta_usec / interval_seconds) / 1000.0
        rates.append(millicores)
    return rates

# Apply to both containers
df['runner_cpu_millicores'] = convert_cpu_to_millicores(df['runner_cpu_usage_usec'].tolist(), interval_seconds)
df['dind_cpu_millicores'] = convert_cpu_to_millicores(df['dind_cpu_usage_usec'].tolist(), interval_seconds)
```

**What this does:**
- Takes cumulative CPU microseconds from cgroups
- Calculates delta between consecutive measurements
- Converts to actual usage rate in millicores
- **Example**: 48,672,534 μs over 24s = 2,028 millicores = 2.03 CPU cores

#### **3. Memory Unit Conversions**
```python
# Convert bytes to MB and GB
df['runner_memory_mb'] = df['runner_memory_current'] / (1024 * 1024)
df['dind_memory_mb'] = df['dind_memory_current'] / (1024 * 1024)
df['runner_memory_gb'] = df['runner_memory_current'] / (1024 * 1024 * 1024)
df['dind_memory_gb'] = df['dind_memory_current'] / (1024 * 1024 * 1024)

# Handle memory limits (convert 'max' to 8GB default)
def safe_convert_limit(limit_val):
    if limit_val == 'max' or pd.isna(limit_val):
        return 8  # Default 8GB limit for visualization
    return limit_val / (1024 * 1024 * 1024)

df['runner_memory_limit_gb'] = df['runner_memory_max'].apply(safe_convert_limit)
df['dind_memory_limit_gb'] = df['dind_memory_max'].apply(safe_convert_limit)
```

#### **4. CPU Throttling Analysis**
```python
# Calculate throttling percentage
df['runner_cpu_throttling_pct'] = np.where(
    df['runner_cpu_nr_periods'] > 0,
    (df['runner_cpu_nr_throttled'] / df['runner_cpu_nr_periods']) * 100,
    0
)
df['dind_cpu_throttling_pct'] = np.where(
    df['dind_cpu_nr_periods'] > 0,
    (df['dind_cpu_nr_throttled'] / df['dind_cpu_nr_periods']) * 100,
    0
)
```

### 📈 **Visualization Mapping**

The script creates 4 visualizations using processed metrics:

#### **1. CPU Usage Over Time (Top Left)**
- **Data Source**: `runner_cpu_millicores`, `dind_cpu_millicores` (calculated)
- **Reference Lines**: 1000m (1 CPU), 2000m (2 CPUs)
- **Purpose**: Show actual CPU consumption patterns

#### **2. Memory Usage vs Limits (Top Right)**
- **Data Source**: `runner_memory_gb`, `dind_memory_gb` (calculated)
- **Limit Lines**: `runner_memory_limit_gb`, `dind_memory_limit_gb` (calculated)
- **Purpose**: Compare usage against configured limits

#### **3. CPU Throttling Events (Bottom Left)**
- **Data Source**: `runner_cpu_throttling_pct`, `dind_cpu_throttling_pct` (calculated)
- **Purpose**: Identify when CPU limits are constraining performance
- **Note**: Shows message if no throttling detected

#### **4. Process Count & System Load (Bottom Right)**
- **Data Source**: `runner_pids_current`, `dind_pids_current`, `runner_load_1min` (direct from CSV)
- **Purpose**: Correlate process activity with system load

### 🧮 **Summary Statistics Calculations**

The script calculates these summary statistics:

#### **CPU Analysis**
```python
runner_cpu_avg = df['runner_cpu_millicores'].mean()
runner_cpu_max = df['runner_cpu_millicores'].max()
dind_cpu_avg = df['dind_cpu_millicores'].mean()
dind_cpu_max = df['dind_cpu_millicores'].max()
```

#### **Memory Analysis**
```python
runner_mem_avg = df['runner_memory_gb'].mean()
runner_mem_max = df['runner_memory_gb'].max()
runner_mem_utilization = (runner_mem_avg / runner_mem_limit) * 100
```

#### **Process and Load Analysis**
```python
runner_pids_avg = df['runner_pids_current'].mean()
runner_pids_max = df['runner_pids_current'].max()
load_avg = df['runner_load_1min'].mean()
load_max = df['runner_load_1min'].max()
```

### ⚠️ **Metrics NOT Used by the Analyzer**

The following CSV metrics are **available but not processed** by the  analyzer:

#### **Detailed Memory Breakdown (6 metrics)**
- `runner_memory_anon`, `runner_memory_file`, `runner_memory_cache`
- `runner_memory_rss`, `runner_memory_swap`
- `runner_memory_pgfault`, `runner_memory_pgmajfault`

**Why not used**: These provide detailed memory breakdown, but the analyzer focuses on overall memory usage patterns.

#### **Detailed CPU Breakdown (4 metrics)**
- `runner_cpu_user_usec`, `runner_cpu_system_usec`
- `runner_cpu_throttled_usec`

**Why not used**: The analyzer uses total CPU usage (`cpu_usage_usec`) rather than user/system breakdown.

#### **Network and Disk Metrics (4 metrics)**
- `runner_network_rx_bytes`, `runner_network_tx_bytes`
- `runner_disk_usage_percent`, `runner_disk_available_kb`

**Why not used**: Focus is on CPU and memory as primary resource constraints.

#### **Pressure Stall Information (9 metrics)**
- All `*_pressure_*` metrics
- **Why not used**: Always 0 in cgroups v1 environments (GitHub Actions runners)

#### **kubectl Metrics (7 metrics)**
- All `kubectl_*` metrics
- **Why not used**: Often unavailable (requires metrics-server), less accurate than cgroup data

### 🎯 **Design Philosophy**

The analyzer focuses on **18 out of 85 metrics** because:

1. **Simplicity**: Avoids overwhelming users with too many metrics
2. **Relevance**: Focuses on metrics that directly impact performance
3. **Accuracy**: Uses cgroup data (more reliable) over kubectl metrics
4. **Actionability**: Provides insights that lead to specific optimization actions

### 🔍 **Debug Information**

When processing data, the script provides debug output:

```
✅ Loaded 3 data points
📊 Detected monitoring interval: 24 seconds
🔍 Sample conversion - Runner:
   CPU delta: 48,672,534 μs over 24s
   Calculated: 2028 millicores (2.03 CPU cores)
   DinD delta: 244,212 μs over 24s
   Calculated: 10 millicores (0.01 CPU cores)
```

This helps verify that:
- Interval detection is working correctly
- CPU conversion calculations are reasonable
- Data quality is good

---

## Output Insights

### 📈 **What the Script Calculates**

1. **CPU Usage Patterns**:
   - Average and peak CPU consumption in millicores
   - Conversion to CPU core equivalents
   - CPU throttling percentage (if limits are set)

2. **Memory Usage Analysis**:
   - Current memory consumption in GB
   - Memory utilization as percentage of limits
   - Memory efficiency insights

3. **System Performance**:
   - Process count trends
   - System load analysis
   - Resource pressure indicators

4. **Resource Efficiency**:
   - Identifies over-provisioned or under-provisioned containers
   - Highlights potential resource contention
   - Suggests optimization opportunities

### 🚨 **Key Alerts and Warnings**

The script provides these insights:

| Condition | Alert | What It Means |
|-----------|-------|---------------|
| CPU > 2000m | 🔥 High CPU usage | Container using more than 2 CPU cores |
| Memory > 80% of limit | 🔥 High memory usage | Risk of out-of-memory errors |
| System load > 4.0 | ⚠️ High system load | System overloaded |
| Throttling > 0% | ⚠️ CPU throttling | CPU limits are constraining performance |

---

## Understanding the Visualizations

### 📊 **CPU Usage Over Time Graph**
- **Y-axis**: CPU usage in millicores
- **Reference lines**: 1000m (1 CPU), 2000m (2 CPUs)
- **What to look for**: Spikes, sustained high usage, patterns

### 📈 **Memory Usage vs Limits Graph**
- **Y-axis**: Memory in GB
- **Solid lines**: Actual usage
- **Dashed lines**: Memory limits
- **What to look for**: Usage approaching limits, memory leaks

### ⚡ **CPU Throttling Events Graph**
- **Y-axis**: Percentage of time throttled
- **What to look for**: Any non-zero values indicate CPU constraints

### 🔧 **Process Count & System Load Graph**
- **Left Y-axis**: Number of processes (PIDs)
- **Right Y-axis**: System load average
- **What to look for**: Process count spikes, load correlation

---

## Practical Examples

### Example 1: Build Process Analysis
```
Runner Container:
- Average: 1,500 millicores (1.5 CPU cores)
- Peak: 3,200 millicores (3.2 CPU cores)
- Memory: 6.2 GB average, 7.8 GB peak
```
**Interpretation**: This is a CPU-intensive build process that occasionally uses over 3 CPU cores. Memory usage is reasonable but approaching the 8GB limit.

### Example 2: Resource Contention
```
System Load: Average 4.2, Peak 6.8
CPU Usage: Runner 800m, DinD 1200m = 2000m total
```
**Interpretation**: High system load despite moderate CPU usage suggests resource contention, possibly I/O bottlenecks.

### Example 3: Memory Pressure
```
Memory Usage: 7.9 GB (98.8% of 8GB limit)
Swap Usage: 512 MB
Page Faults: 15,000 major faults
```
**Interpretation**: Container is running out of memory, using swap, and experiencing performance degradation from disk reads.

---

## Best Practices

### 🎯 **Resource Optimization Tips**

1. **CPU Optimization**:
   - If peak CPU < 1000m consistently, consider reducing CPU requests
   - If CPU throttling > 0%, increase CPU limits
   - High system load with low CPU usage suggests I/O bottlenecks

2. **Memory Optimization**:
   - Keep memory usage < 80% of limits for safety margin
   - Monitor for memory leaks (steadily increasing usage)
   - High major page faults indicate insufficient memory

3. **Monitoring Best Practices**:
   - Monitor during peak workload periods
   - Collect data for at least full build cycles
   - Compare metrics across different node types
   - Track trends over multiple runs

---

## Troubleshooting Common Issues

### ❌ **Problem**: All CPU values are 0
**Solution**: Check if the pod is actually running workloads during monitoring

### ❌ **Problem**: Memory values seem too high
**Solution**: Remember that Linux uses available memory for caching - this is normal

### ❌ **Problem**: Inconsistent throttling values
**Solution**: Throttling only occurs when CPU limits are set and exceeded

### ❌ **Problem**: PSI values always 0
**Solution**: GitHub Actions runners use cgroups v1 which doesn't support PSI

---

## Conclusion

This monitoring system provides comprehensive insights into container resource usage by:

1. **Collecting raw metrics** from cgroups and system interfaces
2. **Converting units** to human-readable formats
3. **Calculating rates** from cumulative counters
4. **Analyzing patterns** to identify optimization opportunities
5. **Visualizing trends** for easy interpretation

Understanding these metrics helps you optimize resource allocation, improve performance, and ensure reliable container operations.
