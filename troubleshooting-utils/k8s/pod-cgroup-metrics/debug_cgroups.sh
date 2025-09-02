#!/bin/bash

# Quick debug script to check cgroup files
# Usage: ./debug_cgroups.sh -n namespace -p pod-name

set -euo pipefail

NAMESPACE=""
POD_NAME=""

# Parse arguments
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
        *)
            echo "Usage: $0 -n NAMESPACE -p POD_NAME"
            exit 1
            ;;
    esac
done

if [[ -z "$NAMESPACE" || -z "$POD_NAME" ]]; then
    echo "Error: Namespace and pod name are required"
    echo "Usage: $0 -n NAMESPACE -p POD_NAME"
    exit 1
fi

echo "=== Debugging cgroup files for $POD_NAME in $NAMESPACE ==="
echo ""

for container in runner dind; do
    echo "--- Container: $container ---"
    kubectl exec "$POD_NAME" -n "$NAMESPACE" -c "$container" -- sh -c '
        echo "=== CGROUP FILE SYSTEM STRUCTURE ==="
        echo "Cgroup v2 check: $([ -f /sys/fs/cgroup/cgroup.controllers ] && echo "v2" || echo "v1")"
        echo ""
        
        echo "Available cgroup subsystems:"
        ls -la /sys/fs/cgroup/ 2>/dev/null || echo "No cgroup directory"
        echo ""
        
        echo "=== CPU FILES ==="
        # Check all possible CPU file locations
        for path in "/sys/fs/cgroup/cpuacct" "/sys/fs/cgroup/cpu,cpuacct" "/sys/fs/cgroup/cpu"; do
            if [ -d "$path" ]; then
                echo "Directory $path exists:"
                ls -la "$path"/ 2>/dev/null | grep -E "(usage|stat)" || echo "  No usage/stat files"
                echo ""
                
                # Show file contents
                for file in "cpuacct.usage" "cpuacct.stat" "cpu.stat"; do
                    filepath="$path/$file"
                    if [ -f "$filepath" ]; then
                        echo "Contents of $filepath:"
                        cat "$filepath" 2>/dev/null || echo "  Cannot read file"
                        echo ""
                    fi
                done
            fi
        done
        
        echo "=== MEMORY FILES ==="
        if [ -d "/sys/fs/cgroup/memory" ]; then
            echo "Memory cgroup files:"
            ls -la /sys/fs/cgroup/memory/ 2>/dev/null | grep -E "(usage|stat|limit)" || echo "  No memory files"
            echo ""
            
            # Show memory file contents
            for file in "memory.usage_in_bytes" "memory.limit_in_bytes" "memory.stat"; do
                filepath="/sys/fs/cgroup/memory/$file"
                if [ -f "$filepath" ]; then
                    echo "Contents of $filepath:"
                    if [ "$file" = "memory.stat" ]; then
                        head -10 "$filepath" 2>/dev/null || echo "  Cannot read file"
                    else
                        cat "$filepath" 2>/dev/null || echo "  Cannot read file"
                    fi
                    echo ""
                fi
            done
        fi
        
        echo "=== PIDS FILES ==="
        if [ -d "/sys/fs/cgroup/pids" ]; then
            echo "PIDs cgroup files:"
            ls -la /sys/fs/cgroup/pids/ 2>/dev/null | grep -E "(current|max)" || echo "  No pids files"
            echo ""
            
            for file in "pids.current" "pids.max"; do
                filepath="/sys/fs/cgroup/pids/$file"
                if [ -f "$filepath" ]; then
                    echo "$filepath: $(cat "$filepath" 2>/dev/null || echo "ERROR")"
                fi
            done
        fi
        echo ""
    '
    echo "============================================"
    echo ""
done
