#!/home/linuxbrew/.linuxbrew/bin/bash
# check_endpoint_connectivity_all_pods.sh
# Usage: ./check_endpoint_connectivity_all_pods.sh <NAMESPACE> <URL> [TIMEOUT_SECONDS] [OUTPUT_CSV] [PARALLEL_JOBS]
# Example: ./check_endpoint_connectivity_all_pods.sh my-namespace http://example.com/health 10 results.csv 5

NAMESPACE="${1:-}"
URL="${2:-}"
TIMEOUT="${3:-10}"
OUTFILE="${4:-pod_endpoint_results.csv}"
PARALLEL="${5:-5}"

if [[ -z "$NAMESPACE" || -z "$URL" ]]; then
  echo "Usage: $0 <NAMESPACE> <URL> [TIMEOUT_SECONDS] [OUTPUT_CSV] [PARALLEL_JOBS]"
  echo "  NAMESPACE: Kubernetes namespace"
  echo "  URL: Endpoint to test"
  echo "  TIMEOUT_SECONDS: Timeout for each request (default: 10)"
  echo "  OUTPUT_CSV: Output CSV file (default: pod_endpoint_results.csv)"
  echo "  PARALLEL_JOBS: Number of parallel jobs (default: 5)"
  exit 2
fi

# CSV header
echo '"PodName","Node","Nodegroup","Time","Status"' > "$OUTFILE"

# Temp directory for parallel execution
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Get list of pods (names and node)
mapfile -t POD_LINES < <(kubectl get pods -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName --no-headers)

if [[ ${#POD_LINES[@]} -eq 0 ]]; then
  echo "No pods found in namespace '$NAMESPACE'."
  exit 0
fi

# Helper: escape for CSV (wrap in quotes, double any internal quotes)
csv_escape() {
  local s="$1"
  s="${s//\"/\"\"}"
  printf '"%s"' "$s"
}

# Function to test a single pod (for parallel execution)
test_pod() {
  local line="$1"
  local namespace="$2"
  local url="$3"
  local timeout="$4"
  local tmpdir="$5"
  
  local podname=$(awk '{print $1}' <<<"$line")
  local nodename=$(awk '{print $2}' <<<"$line")

  # sanitize for filenames
  local pod_safe
  pod_safe="$(printf '%s' "$podname" | tr '/: ' '___')"

  local exec_time
  exec_time=$(date +"%Y-%m-%dT%H:%M:%S%z")

  # nodegroup - consider caching node -> nodegroup outside this function for performance
  local nodegroup
  nodegroup=$(kubectl get node "$nodename" -o jsonpath='{.metadata.labels.eks\.amazonaws\.com/nodegroup}' 2>/dev/null || true)
  [[ -z "$nodegroup" ]] && nodegroup="<none>"

  # remote probe script (uses $TIMEOUT and $URL from env)
  # Added --insecure/-k for HTTPS to bypass certificate validation
  local probe_script
  probe_script=$'if command -v curl >/dev/null 2>&1; then\n  result=$(curl -L --insecure --max-time $TIMEOUT --silent --show-error --output /dev/null --write-out "HTTP_CODE:%{http_code}|EXIT_CODE:%{exitcode}|EFFECTIVE_URL:%{url_effective}" "$URL" 2>&1)\n  code=$(echo "$result" | grep -oP "HTTP_CODE:\\K[0-9]+" || echo "000")\n  if [ "$code" = "000" ]; then\n    error=$(echo "$result" | head -n1 | cut -c1-100)\n    printf "000_[%s]" "$error"\n  else\n    printf "%s" "$code"\n  fi\n  exit 0\nelif command -v wget >/dev/null 2>&1; then\n  result=$(wget --no-check-certificate --timeout=$TIMEOUT --tries=1 --output-document=/dev/null --server-response "$URL" 2>&1)\n  code=$(echo "$result" | awk \'/HTTP\\//{c=$2} END{print c}\')\n  if [ -n "$code" ]; then printf "%s" "$code"; else printf "000_[wget_failed]"; fi\n  exit 0\nelse\n  printf "NO_TOOL"; exit 127; fi'

  # temp files
  local tmpout="$tmpdir/out_${pod_safe}_$$"
  local tmperr="$tmpdir/err_${pod_safe}_$$"
  local exit_code=0
  local out=""
  local errtxt=""

  # Run probe inside pod; pass URL and TIMEOUT as env (safer than inlining)
  if command -v timeout >/dev/null 2>&1; then
    timeout 60s kubectl exec -n "$namespace" "$podname" -- env TIMEOUT="$timeout" URL="$url" sh -c "$probe_script" >"$tmpout" 2>"$tmperr" || true
    exit_code=$?
  else
    kubectl exec -n "$namespace" "$podname" -- env TIMEOUT="$timeout" URL="$url" sh -c "$probe_script" >"$tmpout" 2>"$tmperr" || true
    exit_code=$?
  fi

  out=$(cat "$tmpout" 2>/dev/null || true)
  errtxt=$(cat "$tmperr" 2>/dev/null || true)

  # If multi-container pod error detected, retry with first container
  if echo "$errtxt" | grep -qi -E "container name must be specified|one of the containers|please specify the container"; then
    local container
    container=$(kubectl get pod -n "$namespace" "$podname" -o jsonpath='{.spec.containers[0].name}' 2>/dev/null || true)
    if [[ -n "$container" ]]; then
      if command -v timeout >/dev/null 2>&1; then
        timeout 60s kubectl exec -n "$namespace" -c "$container" "$podname" -- env TIMEOUT="$timeout" URL="$url" sh -c "$probe_script" >"$tmpout" 2>/dev/null || true
        exit_code=$?
      else
        kubectl exec -n "$namespace" -c "$container" "$podname" -- env TIMEOUT="$timeout" URL="$url" sh -c "$probe_script" >"$tmpout" 2>/dev/null || true
        exit_code=$?
      fi
      out=$(cat "$tmpout" 2>/dev/null || true)
    fi
  fi

  rm -f "$tmpout" "$tmperr" || true

  # Normalize result
  local status
  status="$(echo -n "$out" | tr -d '\r\n' || true)"

  if [[ "$status" == "NO_TOOL" ]]; then
    status="NO_TOOL"
  elif [[ $exit_code -ne 0 ]]; then
    if [[ $exit_code -eq 28 || $exit_code -eq 124 ]]; then
      status="TIMEOUT"
    elif [[ "$status" =~ ^[0-9]{3}$ ]]; then
      : # keep numeric
    else
      # try to include a short form of stderr if useful (optional)
      status="ERROR_${exit_code}"
    fi
  elif [[ -z "$status" ]]; then
    status="ERROR_empty"
  fi

  # write one-line CSV to per-pod result file (overwrite)
  local result_file="$tmpdir/result_${pod_safe}.csv"
  printf "%s,%s,%s,%s,%s\n" \
    "$(csv_escape "$podname")" \
    "$(csv_escape "$nodename")" \
    "$(csv_escape "$nodegroup")" \
    "$(csv_escape "$exec_time")" \
    "$(csv_escape "$status")" > "$result_file"

  echo "✓ Pod: $podname | Node: $nodename | Nodegroup: $nodegroup | Status: $status"
}

# Export function and variables for parallel execution
export -f test_pod csv_escape
export NAMESPACE URL TIMEOUT TMPDIR

echo "Testing ${#POD_LINES[@]} pods with $PARALLEL parallel jobs..."
echo ""

# Run tests in parallel using xargs
printf "%s\n" "${POD_LINES[@]}" | \
  xargs -I {} -P "$PARALLEL" bash -c 'test_pod "$@"' _ {} "$NAMESPACE" "$URL" "$TIMEOUT" "$TMPDIR"

# Collect all results into final CSV (sorted by pod name)
for f in "$TMPDIR"/result_*.csv; do
  [[ -f "$f" ]] && cat "$f" >> "$OUTFILE"
done

echo ""
echo "================================"
echo "Results written to: $OUTFILE"
echo "Total pods tested: ${#POD_LINES[@]}"
echo "Parallel jobs: $PARALLEL"
echo "================================"
