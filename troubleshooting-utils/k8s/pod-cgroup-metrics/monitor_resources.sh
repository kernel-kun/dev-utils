#!/bin/bash

# Resource Monitoring Script for GitHub Actions Runner Pod
# Monitors CPU, Memory, Storage, and Network metrics to identify noisy neighbor issues

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-default}"
POD_NAME="${POD_NAME:-}"
OUTPUT_DIR="${OUTPUT_DIR:-./monitoring_output}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-2}"
DURATION_MINUTES="${DURATION_MINUTES:-60}"
CSV_FILE="${OUTPUT_DIR}/resource_metrics_$(date +%Y%m%d_%H%M%S).csv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# Function to show usage
usage() {
    cat << EOF
Usage: $0 -n NAMESPACE -p POD_NAME [OPTIONS]

Required:
  -n, --namespace NAMESPACE    Kubernetes namespace
  -p, --pod POD_NAME          Pod name to monitor

Options:
  -i, --interval SECONDS      Monitoring interval in seconds (default: 2)
  -d, --duration MINUTES      Duration to monitor in minutes (default: 60)
  -o, --output-dir DIR        Output directory (default: ./monitoring_output)
  -h, --help                  Show this help

Examples:
  $0 -n github-actions -p runner-abc123
  $0 -n default -p runner-xyz789 -i 5 -d 30

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -p|--pod)
            POD_NAME="$2"
            shift 2
            ;;
        -i|--interval)
            INTERVAL_SECONDS="$2"
            shift 2
            ;;
        -d|--duration)
            DURATION_MINUTES="$2"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$NAMESPACE" || -z "$POD_NAME" ]]; then
    log_error "Namespace and pod name are required"
    usage
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
CSV_FILE="${OUTPUT_DIR}/resource_metrics_$(date +%Y%m%d_%H%M%S).csv"

log_info "Starting resource monitoring for pod: $POD_NAME in namespace: $NAMESPACE"
log_info "Output file: $CSV_FILE"
log_info "Monitoring interval: ${INTERVAL_SECONDS}s, Duration: ${DURATION_MINUTES}m"

# Function to check if pod exists and get containers
check_pod() {
    if ! kubectl get pod "$POD_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Pod $POD_NAME not found in namespace $NAMESPACE"
        exit 1
    fi
    
    local containers
    containers=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.containers[*].name}')
    log_info "Found containers: $containers"
    
    # Check if runner and dind containers exist
    if [[ ! $containers =~ "runner" ]]; then
        log_warn "Container 'runner' not found in pod"
    fi
    if [[ ! $containers =~ "dind" ]]; then
        log_warn "Container 'dind' not found in pod"
    fi
}

# Function to get cgroup metrics from container - simplified version
get_cgroup_metrics() {
    local container="$1"
    
    # Execute a simplified script inside the container that uses basic shell commands
    local exec_result
    if exec_result=$(kubectl exec "$POD_NAME" -n "$NAMESPACE" -c "$container" -- sh -c '
        # Check if cgroup v2 or v1
        if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
            echo "CGROUP_VERSION=v2"
            # For v2, most metrics should be available, but lets focus on the basic ones
            echo "CPU_USAGE_USEC=0"
            echo "CPU_USER_USEC=0"
            echo "CPU_SYSTEM_USEC=0"
            echo "MEMORY_CURRENT=0"
            echo "MEMORY_MAX=max"
        else
            echo "CGROUP_VERSION=v1"
            
            # CPU usage from cpuacct.usage (nanoseconds -> microseconds)
            if [ -f /sys/fs/cgroup/cpu,cpuacct/cpuacct.usage ]; then
                CPU_USAGE_NS=$(cat /sys/fs/cgroup/cpu,cpuacct/cpuacct.usage 2>/dev/null || echo "0")
                echo "CPU_USAGE_USEC=$((CPU_USAGE_NS / 1000))"
            else
                echo "CPU_USAGE_USEC=0"
            fi
            
            # CPU user/system from cpuacct.stat (jiffies -> microseconds)
            if [ -f /sys/fs/cgroup/cpu,cpuacct/cpuacct.stat ]; then
                USER_JIFFIES=$(cat /sys/fs/cgroup/cpu,cpuacct/cpuacct.stat | grep "^user " | cut -d" " -f2 2>/dev/null || echo "0")
                SYSTEM_JIFFIES=$(cat /sys/fs/cgroup/cpu,cpuacct/cpuacct.stat | grep "^system " | cut -d" " -f2 2>/dev/null || echo "0")
                echo "CPU_USER_USEC=$((USER_JIFFIES * 10000))"
                echo "CPU_SYSTEM_USEC=$((SYSTEM_JIFFIES * 10000))"
            else
                echo "CPU_USER_USEC=0"
                echo "CPU_SYSTEM_USEC=0"
            fi
            
            # Memory usage
            if [ -f /sys/fs/cgroup/memory/memory.usage_in_bytes ]; then
                echo "MEMORY_CURRENT=$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || echo "0")"
            else
                echo "MEMORY_CURRENT=0"
            fi
            
            # Memory limit
            if [ -f /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
                LIMIT=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo "0")
                if [ "$LIMIT" -gt 9000000000000000000 ] 2>/dev/null; then
                    echo "MEMORY_MAX=max"
                else
                    echo "MEMORY_MAX=$LIMIT"
                fi
            else
                echo "MEMORY_MAX=max"
            fi
            
            # Memory breakdown from memory.stat
            if [ -f /sys/fs/cgroup/memory/memory.stat ]; then
                RSS=$(cat /sys/fs/cgroup/memory/memory.stat | grep "^rss " | cut -d" " -f2 2>/dev/null || echo "0")
                CACHE=$(cat /sys/fs/cgroup/memory/memory.stat | grep "^cache " | cut -d" " -f2 2>/dev/null || echo "0")
                SWAP=$(cat /sys/fs/cgroup/memory/memory.stat | grep "^swap " | cut -d" " -f2 2>/dev/null || echo "0")
                # Get actual page fault metrics
                PGFAULT=$(cat /sys/fs/cgroup/memory/memory.stat | grep "^pgfault " | cut -d" " -f2 2>/dev/null || echo "0")
                PGMAJFAULT=$(cat /sys/fs/cgroup/memory/memory.stat | grep "^pgmajfault " | cut -d" " -f2 2>/dev/null || echo "0")
                echo "MEMORY_RSS=$RSS"
                echo "MEMORY_CACHE=$CACHE"
                echo "MEMORY_SWAP=$SWAP"
                echo "MEMORY_ANON=$RSS"
                echo "MEMORY_FILE=$CACHE"
                echo "MEMORY_PGFAULT=$PGFAULT"
                echo "MEMORY_PGMAJFAULT=$PGMAJFAULT"
            else
                echo "MEMORY_RSS=0"
                echo "MEMORY_CACHE=0"
                echo "MEMORY_SWAP=0"
                echo "MEMORY_ANON=0"
                echo "MEMORY_FILE=0"
                echo "MEMORY_PGFAULT=0"
                echo "MEMORY_PGMAJFAULT=0"
            fi
            
            # PIDs
            if [ -f /sys/fs/cgroup/pids/pids.current ]; then
                echo "PIDS_CURRENT=$(cat /sys/fs/cgroup/pids/pids.current 2>/dev/null || echo "0")"
            else
                echo "PIDS_CURRENT=0"
            fi
            
            if [ -f /sys/fs/cgroup/pids/pids.max ]; then
                echo "PIDS_MAX=$(cat /sys/fs/cgroup/pids/pids.max 2>/dev/null || echo "max")"
            else
                echo "PIDS_MAX=max"
            fi
        fi
        
            # CPU throttling from cpu.stat (if available)
            if [ -f /sys/fs/cgroup/cpu,cpuacct/cpu.stat ]; then
                NR_PERIODS=$(cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | grep "^nr_periods " | cut -d" " -f2 2>/dev/null || echo "0")
                NR_THROTTLED=$(cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | grep "^nr_throttled " | cut -d" " -f2 2>/dev/null || echo "0")
                THROTTLED_TIME=$(cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | grep "^throttled_time " | cut -d" " -f2 2>/dev/null || echo "0")
                echo "CPU_NR_PERIODS=$NR_PERIODS"
                echo "CPU_NR_THROTTLED=$NR_THROTTLED"
                echo "CPU_THROTTLED_USEC=$((THROTTLED_TIME / 1000))"
            else
                echo "CPU_NR_PERIODS=0"
                echo "CPU_NR_THROTTLED=0"
                echo "CPU_THROTTLED_USEC=0"
            fi
        echo "CPU_PRESSURE_SOME_AVG10=0"
        echo "CPU_PRESSURE_SOME_AVG60=0"
        echo "CPU_PRESSURE_SOME_TOTAL=0"
        echo "MEMORY_PRESSURE_SOME_AVG10=0"
        echo "MEMORY_PRESSURE_SOME_AVG60=0"
        echo "MEMORY_PRESSURE_FULL_AVG10=0"
        echo "MEMORY_PRESSURE_FULL_AVG60=0"
        echo "IO_PRESSURE_SOME_AVG10=0"
        echo "IO_PRESSURE_FULL_AVG10=0"
        
        # System metrics  
        echo "LOAD_1MIN=$(cat /proc/loadavg | cut -d" " -f1 2>/dev/null || echo "0")"
        echo "LOAD_5MIN=$(cat /proc/loadavg | cut -d" " -f2 2>/dev/null || echo "0")"
        echo "LOAD_15MIN=$(cat /proc/loadavg | cut -d" " -f3 2>/dev/null || echo "0")"
        
        # Disk usage
        DISK_INFO=$(df / 2>/dev/null | tail -1)
        if [ -n "$DISK_INFO" ]; then
            echo "DISK_USAGE_PERCENT=$(echo "$DISK_INFO" | awk "{print \$5}" | sed "s/%//" || echo "0")"
            echo "DISK_AVAILABLE_KB=$(echo "$DISK_INFO" | awk "{print \$4}" || echo "0")"
        else
            echo "DISK_USAGE_PERCENT=0"
            echo "DISK_AVAILABLE_KB=0"
        fi
        
        # Network stats - try to find the main network interface
        if [ -f /proc/net/dev ]; then
            # Look for common interface names, skip loopback
            NET_LINE=$(cat /proc/net/dev | grep -E "eth0|ens|enp|wlan" | head -1 2>/dev/null)
            if [ -n "$NET_LINE" ]; then
                echo "NETWORK_RX_BYTES=$(echo "$NET_LINE" | awk "{print \$2}" || echo "0")"
                echo "NETWORK_TX_BYTES=$(echo "$NET_LINE" | awk "{print \$10}" || echo "0")"
            else
                echo "NETWORK_RX_BYTES=0"
                echo "NETWORK_TX_BYTES=0"
            fi
        else
            echo "NETWORK_RX_BYTES=0"
            echo "NETWORK_TX_BYTES=0"
        fi
        echo "PROCESS_COUNT=$(ps aux 2>/dev/null | wc -l || echo "0")"
        echo "FD_COUNT=0"
        
    ' 2>/dev/null); then
        echo "$exec_result"
    else
        log_warn "Failed to get cgroup metrics from container $container"
        echo "ERROR=failed_to_exec"
    fi
}

# Function to get pod-level metrics from kubectl
get_pod_metrics() {
    local pod_data
    if pod_data=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o json 2>/dev/null); then
        # Extract pod phase and status
        local phase
        phase=$(echo "$pod_data" | jq -r '.status.phase // "Unknown"')
        echo "POD_PHASE=$phase"
        
        # Extract container statuses
        local container_count ready_count
        container_count=$(echo "$pod_data" | jq '.status.containerStatuses | length // 0')
        ready_count=$(echo "$pod_data" | jq '[.status.containerStatuses[]? | select(.ready == true)] | length // 0')
        echo "CONTAINER_COUNT=$container_count"
        echo "READY_CONTAINERS=$ready_count"
        
        # Extract restart counts
        local total_restarts
        total_restarts=$(echo "$pod_data" | jq '[.status.containerStatuses[]?.restartCount // 0] | add // 0')
        echo "TOTAL_RESTARTS=$total_restarts"
        
        # Node information
        local node_name
        node_name=$(echo "$pod_data" | jq -r '.spec.nodeName // "Unknown"')
        echo "NODE_NAME=$node_name"
        
    else
        log_warn "Failed to get pod metrics from kubectl"
        echo "POD_ERROR=failed_to_get_pod_data"
    fi
}

# Global variable to track metrics API availability
METRICS_API_AVAILABLE=""

# Function to check if Metrics API is available
check_metrics_api() {
    if [[ -n "$METRICS_API_AVAILABLE" ]]; then
        # Already checked, return cached result
        [[ "$METRICS_API_AVAILABLE" == "true" ]]
        return $?
    fi
    
    # Check if metrics.k8s.io API is available
    if kubectl api-resources --api-group=metrics.k8s.io >/dev/null 2>&1; then
        # Double-check by trying to get node metrics
        if kubectl top nodes --no-headers >/dev/null 2>&1; then
            METRICS_API_AVAILABLE="true"
            log_info "Metrics API is available - will collect kubectl top metrics"
            return 0
        fi
    fi
    
    METRICS_API_AVAILABLE="false"
    log_warn "Metrics API not available - skipping kubectl top metrics (install metrics-server if needed)"
    return 1
}

# Function to get resource usage from kubectl top
get_kubectl_top_metrics() {
    # Check if Metrics API is available
    if ! check_metrics_api; then
        echo "KUBECTL_METRICS_AVAILABLE=false"
        return 0
    fi
    
    echo "KUBECTL_METRICS_AVAILABLE=true"
    
    local pod_metrics containers_metrics
    
    # Pod-level metrics
    if pod_metrics=$(kubectl top pod "$POD_NAME" -n "$NAMESPACE" --no-headers 2>/dev/null); then
        local cpu_usage memory_usage
        cpu_usage=$(echo "$pod_metrics" | awk '{print $2}' | sed 's/m$//')
        memory_usage=$(echo "$pod_metrics" | awk '{print $3}' | sed 's/Mi$//')
        echo "KUBECTL_CPU_MILLICORES=$cpu_usage"
        echo "KUBECTL_MEMORY_MB=$memory_usage"
    else
        log_warn "Failed to get pod metrics from kubectl top"
        echo "KUBECTL_CPU_MILLICORES=0"
        echo "KUBECTL_MEMORY_MB=0"
    fi
    
    # Container-level metrics
    if containers_metrics=$(kubectl top pod "$POD_NAME" -n "$NAMESPACE" --containers --no-headers 2>/dev/null); then
        while IFS= read -r line; do
            local container_name cpu_usage memory_usage
            container_name=$(echo "$line" | awk '{print $2}')
            cpu_usage=$(echo "$line" | awk '{print $3}' | sed 's/m$//')
            memory_usage=$(echo "$line" | awk '{print $4}' | sed 's/Mi$//')
            echo "KUBECTL_${container_name^^}_CPU_MILLICORES=$cpu_usage"
            echo "KUBECTL_${container_name^^}_MEMORY_MB=$memory_usage"
        done <<< "$containers_metrics"
    else
        log_warn "Failed to get container metrics from kubectl top"
        # Provide default values for known containers
        echo "KUBECTL_RUNNER_CPU_MILLICORES=0"
        echo "KUBECTL_RUNNER_MEMORY_MB=0"
        echo "KUBECTL_DIND_CPU_MILLICORES=0"
        echo "KUBECTL_DIND_MEMORY_MB=0"
    fi
}

# Function to create CSV header
create_csv_header() {
    cat > "$CSV_FILE" << 'EOF'
timestamp,pod_phase,container_count,ready_containers,total_restarts,node_name,kubectl_metrics_available,kubectl_cpu_millicores,kubectl_memory_mb,kubectl_runner_cpu_millicores,kubectl_runner_memory_mb,kubectl_dind_cpu_millicores,kubectl_dind_memory_mb,runner_cgroup_version,runner_cpu_usage_usec,runner_cpu_user_usec,runner_cpu_system_usec,runner_cpu_nr_periods,runner_cpu_nr_throttled,runner_cpu_throttled_usec,runner_memory_current,runner_memory_max,runner_memory_anon,runner_memory_file,runner_memory_cache,runner_memory_rss,runner_memory_swap,runner_memory_pgfault,runner_memory_pgmajfault,runner_cpu_pressure_some_avg10,runner_cpu_pressure_some_avg60,runner_cpu_pressure_some_total,runner_memory_pressure_some_avg10,runner_memory_pressure_some_avg60,runner_memory_pressure_full_avg10,runner_memory_pressure_full_avg60,runner_io_pressure_some_avg10,runner_io_pressure_full_avg10,runner_pids_current,runner_pids_max,runner_load_1min,runner_load_5min,runner_load_15min,runner_disk_usage_percent,runner_disk_available_kb,runner_network_rx_bytes,runner_network_tx_bytes,runner_process_count,runner_fd_count,dind_cgroup_version,dind_cpu_usage_usec,dind_cpu_user_usec,dind_cpu_system_usec,dind_cpu_nr_periods,dind_cpu_nr_throttled,dind_cpu_throttled_usec,dind_memory_current,dind_memory_max,dind_memory_anon,dind_memory_file,dind_memory_cache,dind_memory_rss,dind_memory_swap,dind_memory_pgfault,dind_memory_pgmajfault,dind_cpu_pressure_some_avg10,dind_cpu_pressure_some_avg60,dind_cpu_pressure_some_total,dind_memory_pressure_some_avg10,dind_memory_pressure_some_avg60,dind_memory_pressure_full_avg10,dind_memory_pressure_full_avg60,dind_io_pressure_some_avg10,dind_io_pressure_full_avg10,dind_pids_current,dind_pids_max,dind_load_1min,dind_load_5min,dind_load_15min,dind_disk_usage_percent,dind_disk_available_kb,dind_network_rx_bytes,dind_network_tx_bytes,dind_process_count,dind_fd_count
EOF
}

# Function to collect and write metrics
collect_metrics() {
    local timestamp
    timestamp=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
    
    # Collect all metrics
    local pod_metrics kubectl_metrics runner_metrics dind_metrics
    
    # Get pod-level metrics
    pod_metrics=$(get_pod_metrics)
    kubectl_metrics=$(get_kubectl_top_metrics)
    
    # Get container-specific metrics
    runner_metrics=$(get_cgroup_metrics "runner" | sed 's/^/RUNNER_/')
    dind_metrics=$(get_cgroup_metrics "dind" | sed 's/^/DIND_/')
    
    # Combine all metrics
    local all_metrics
    all_metrics=$(cat << EOF
$pod_metrics
$kubectl_metrics
$runner_metrics
$dind_metrics
EOF
)
    
    # Parse metrics into associative array
    declare -A metrics
    while IFS='=' read -r key value; do
        [[ -n "$key" && -n "$value" ]] && metrics["$key"]="$value"
    done <<< "$all_metrics"
    
    # Write CSV row
    printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
        "$timestamp" \
        "${metrics[POD_PHASE]:-Unknown}" \
        "${metrics[CONTAINER_COUNT]:-0}" \
        "${metrics[READY_CONTAINERS]:-0}" \
        "${metrics[TOTAL_RESTARTS]:-0}" \
        "${metrics[NODE_NAME]:-Unknown}" \
        "${metrics[KUBECTL_METRICS_AVAILABLE]:-false}" \
        "${metrics[KUBECTL_CPU_MILLICORES]:-0}" \
        "${metrics[KUBECTL_MEMORY_MB]:-0}" \
        "${metrics[KUBECTL_RUNNER_CPU_MILLICORES]:-0}" \
        "${metrics[KUBECTL_RUNNER_MEMORY_MB]:-0}" \
        "${metrics[KUBECTL_DIND_CPU_MILLICORES]:-0}" \
        "${metrics[KUBECTL_DIND_MEMORY_MB]:-0}" \
        "${metrics[RUNNER_CGROUP_VERSION]:-unknown}" \
        "${metrics[RUNNER_CPU_USAGE_USEC]:-0}" \
        "${metrics[RUNNER_CPU_USER_USEC]:-0}" \
        "${metrics[RUNNER_CPU_SYSTEM_USEC]:-0}" \
        "${metrics[RUNNER_CPU_NR_PERIODS]:-0}" \
        "${metrics[RUNNER_CPU_NR_THROTTLED]:-0}" \
        "${metrics[RUNNER_CPU_THROTTLED_USEC]:-0}" \
        "${metrics[RUNNER_MEMORY_CURRENT]:-0}" \
        "${metrics[RUNNER_MEMORY_MAX]:-max}" \
        "${metrics[RUNNER_MEMORY_ANON]:-0}" \
        "${metrics[RUNNER_MEMORY_FILE]:-0}" \
        "${metrics[RUNNER_MEMORY_CACHE]:-0}" \
        "${metrics[RUNNER_MEMORY_RSS]:-0}" \
        "${metrics[RUNNER_MEMORY_SWAP]:-0}" \
        "${metrics[RUNNER_MEMORY_PGFAULT]:-0}" \
        "${metrics[RUNNER_MEMORY_PGMAJFAULT]:-0}" \
        "${metrics[RUNNER_CPU_PRESSURE_SOME_AVG10]:-0}" \
        "${metrics[RUNNER_CPU_PRESSURE_SOME_AVG60]:-0}" \
        "${metrics[RUNNER_CPU_PRESSURE_SOME_TOTAL]:-0}" \
        "${metrics[RUNNER_MEMORY_PRESSURE_SOME_AVG10]:-0}" \
        "${metrics[RUNNER_MEMORY_PRESSURE_SOME_AVG60]:-0}" \
        "${metrics[RUNNER_MEMORY_PRESSURE_FULL_AVG10]:-0}" \
        "${metrics[RUNNER_MEMORY_PRESSURE_FULL_AVG60]:-0}" \
        "${metrics[RUNNER_IO_PRESSURE_SOME_AVG10]:-0}" \
        "${metrics[RUNNER_IO_PRESSURE_FULL_AVG10]:-0}" \
        "${metrics[RUNNER_PIDS_CURRENT]:-0}" \
        "${metrics[RUNNER_PIDS_MAX]:-max}" \
        "${metrics[RUNNER_LOAD_1MIN]:-0}" \
        "${metrics[RUNNER_LOAD_5MIN]:-0}" \
        "${metrics[RUNNER_LOAD_15MIN]:-0}" \
        "${metrics[RUNNER_DISK_USAGE_PERCENT]:-0}" \
        "${metrics[RUNNER_DISK_AVAILABLE_KB]:-0}" \
        "${metrics[RUNNER_NETWORK_RX_BYTES]:-0}" \
        "${metrics[RUNNER_NETWORK_TX_BYTES]:-0}" \
        "${metrics[RUNNER_PROCESS_COUNT]:-0}" \
        "${metrics[RUNNER_FD_COUNT]:-0}" \
        "${metrics[DIND_CGROUP_VERSION]:-unknown}" \
        "${metrics[DIND_CPU_USAGE_USEC]:-0}" \
        "${metrics[DIND_CPU_USER_USEC]:-0}" \
        "${metrics[DIND_CPU_SYSTEM_USEC]:-0}" \
        "${metrics[DIND_CPU_NR_PERIODS]:-0}" \
        "${metrics[DIND_CPU_NR_THROTTLED]:-0}" \
        "${metrics[DIND_CPU_THROTTLED_USEC]:-0}" \
        "${metrics[DIND_MEMORY_CURRENT]:-0}" \
        "${metrics[DIND_MEMORY_MAX]:-max}" \
        "${metrics[DIND_MEMORY_ANON]:-0}" \
        "${metrics[DIND_MEMORY_FILE]:-0}" \
        "${metrics[DIND_MEMORY_CACHE]:-0}" \
        "${metrics[DIND_MEMORY_RSS]:-0}" \
        "${metrics[DIND_MEMORY_SWAP]:-0}" \
        "${metrics[DIND_MEMORY_PGFAULT]:-0}" \
        "${metrics[DIND_MEMORY_PGMAJFAULT]:-0}" \
        "${metrics[DIND_CPU_PRESSURE_SOME_AVG10]:-0}" \
        "${metrics[DIND_CPU_PRESSURE_SOME_AVG60]:-0}" \
        "${metrics[DIND_CPU_PRESSURE_SOME_TOTAL]:-0}" \
        "${metrics[DIND_MEMORY_PRESSURE_SOME_AVG10]:-0}" \
        "${metrics[DIND_MEMORY_PRESSURE_SOME_AVG60]:-0}" \
        "${metrics[DIND_MEMORY_PRESSURE_FULL_AVG10]:-0}" \
        "${metrics[DIND_MEMORY_PRESSURE_FULL_AVG60]:-0}" \
        "${metrics[DIND_IO_PRESSURE_SOME_AVG10]:-0}" \
        "${metrics[DIND_IO_PRESSURE_FULL_AVG10]:-0}" \
        "${metrics[DIND_PIDS_CURRENT]:-0}" \
        "${metrics[DIND_PIDS_MAX]:-max}" \
        "${metrics[DIND_LOAD_1MIN]:-0}" \
        "${metrics[DIND_LOAD_5MIN]:-0}" \
        "${metrics[DIND_LOAD_15MIN]:-0}" \
        "${metrics[DIND_DISK_USAGE_PERCENT]:-0}" \
        "${metrics[DIND_DISK_AVAILABLE_KB]:-0}" \
        "${metrics[DIND_NETWORK_RX_BYTES]:-0}" \
        "${metrics[DIND_NETWORK_TX_BYTES]:-0}" \
        "${metrics[DIND_PROCESS_COUNT]:-0}" \
        "${metrics[DIND_FD_COUNT]:-0}" \
        >> "$CSV_FILE"
}

# Function to display real-time metrics
display_metrics() {
    local iteration="$1"
    local total_iterations="$2"
    
    clear
    echo "=================================="
    echo "  Resource Monitor Dashboard"
    echo "=================================="
    echo "Pod: $POD_NAME | Namespace: $NAMESPACE"
    echo "Progress: $iteration/$total_iterations ($(( iteration * 100 / total_iterations ))%)"
    echo "Output: $CSV_FILE"
    echo ""
    
    # Get latest metrics for display
    local pod_metrics kubectl_metrics runner_metrics dind_metrics
    pod_metrics=$(get_pod_metrics)
    kubectl_metrics=$(get_kubectl_top_metrics)
    runner_metrics=$(get_cgroup_metrics "runner")
    dind_metrics=$(get_cgroup_metrics "dind")
    
    # Parse metrics for display
    declare -A metrics
    while IFS='=' read -r key value; do
        [[ -n "$key" && -n "$value" ]] && metrics["$key"]="$value"
    done <<< "$(echo -e "$pod_metrics\n$kubectl_metrics\nRUNNER_$runner_metrics\nDIND_$dind_metrics")"
    
    # Display key metrics
    echo "📊 Pod Status:"
    echo "  Phase: ${metrics[POD_PHASE]:-Unknown}"
    echo "  Containers Ready: ${metrics[READY_CONTAINERS]:-0}/${metrics[CONTAINER_COUNT]:-0}"
    echo "  Total Restarts: ${metrics[TOTAL_RESTARTS]:-0}"
    echo "  Node: ${metrics[NODE_NAME]:-Unknown}"
    echo ""
    
    echo "⚡ Resource Usage (kubectl top):"
    echo "  Total CPU: ${metrics[KUBECTL_CPU_MILLICORES]:-0}m"
    echo "  Total Memory: ${metrics[KUBECTL_MEMORY_MB]:-0}Mi"
    echo "  Runner CPU: ${metrics[KUBECTL_RUNNER_CPU_MILLICORES]:-0}m"
    echo "  Runner Memory: ${metrics[KUBECTL_RUNNER_MEMORY_MB]:-0}Mi"
    echo "  DinD CPU: ${metrics[KUBECTL_DIND_CPU_MILLICORES]:-0}m"
    echo "  DinD Memory: ${metrics[KUBECTL_DIND_MEMORY_MB]:-0}Mi"
    echo ""
    
    echo "🧠 Memory Pressure (PSI):"
    echo "  Runner Mem Pressure (10s avg): ${metrics[RUNNER_MEMORY_PRESSURE_SOME_AVG10]:-0}%"
    echo "  Runner Mem Full (10s avg): ${metrics[RUNNER_MEMORY_PRESSURE_FULL_AVG10]:-0}%"
    echo "  DinD Mem Pressure (10s avg): ${metrics[DIND_MEMORY_PRESSURE_SOME_AVG10]:-0}%"
    echo "  DinD Mem Full (10s avg): ${metrics[DIND_MEMORY_PRESSURE_FULL_AVG10]:-0}%"
    echo ""
    
    echo "🖥️  CPU Pressure (PSI):"
    echo "  Runner CPU Pressure (10s avg): ${metrics[RUNNER_CPU_PRESSURE_SOME_AVG10]:-0}%"
    echo "  DinD CPU Pressure (10s avg): ${metrics[DIND_CPU_PRESSURE_SOME_AVG10]:-0}%"
    echo ""
    
    echo "💾 I/O Pressure (PSI):"
    echo "  Runner I/O Pressure (10s avg): ${metrics[RUNNER_IO_PRESSURE_SOME_AVG10]:-0}%"
    echo "  DinD I/O Pressure (10s avg): ${metrics[DIND_IO_PRESSURE_SOME_AVG10]:-0}%"
    echo ""
    
    echo "📈 System Load:"
    echo "  Runner Load (1/5/15m): ${metrics[RUNNER_LOAD_1MIN]:-0}/${metrics[RUNNER_LOAD_5MIN]:-0}/${metrics[RUNNER_LOAD_15MIN]:-0}"
    echo "  DinD Load (1/5/15m): ${metrics[DIND_LOAD_1MIN]:-0}/${metrics[DIND_LOAD_5MIN]:-0}/${metrics[DIND_LOAD_15MIN]:-0}"
    echo ""
    
    echo "💽 Storage:"
    echo "  Runner Disk Usage: ${metrics[RUNNER_DISK_USAGE_PERCENT]:-0}%"
    echo "  DinD Disk Usage: ${metrics[DIND_DISK_USAGE_PERCENT]:-0}%"
    echo ""
    
    echo "🔧 Process/File Descriptors:"
    echo "  Runner Processes: ${metrics[RUNNER_PROCESS_COUNT]:-0}"
    echo "  DinD Processes: ${metrics[DIND_PROCESS_COUNT]:-0}"
    echo "  Runner PIDs: ${metrics[RUNNER_PIDS_CURRENT]:-0}/${metrics[RUNNER_PIDS_MAX]:-max}"
    echo "  DinD PIDs: ${metrics[DIND_PIDS_CURRENT]:-0}/${metrics[DIND_PIDS_MAX]:-max}"
    echo ""
    
    echo "Press Ctrl+C to stop monitoring..."
}

# Signal handlers
cleanup() {
    log_info "Monitoring stopped. Data saved to: $CSV_FILE"
    log_success "Monitoring completed successfully!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Main monitoring loop
main() {
    # Initial checks
    check_pod
    
    # Create CSV file with header
    create_csv_header
    log_success "CSV file created: $CSV_FILE"
    
    # Calculate total iterations
    local total_iterations
    total_iterations=$(( DURATION_MINUTES * 60 / INTERVAL_SECONDS ))
    
    log_info "Starting monitoring loop..."
    log_info "Total iterations planned: $total_iterations"
    
    # Monitoring loop
    for ((i=1; i<=total_iterations; i++)); do
        # Collect and save metrics
        collect_metrics
        
        # Display dashboard
        display_metrics "$i" "$total_iterations"
        
        # Sleep for interval (unless it's the last iteration)
        if [[ $i -lt $total_iterations ]]; then
            sleep "$INTERVAL_SECONDS"
        fi
    done
    
    cleanup
}

# Start monitoring
main
