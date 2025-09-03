#!/bin/bash

# Artifactory Docker Authentication Script
# Adds Docker registry authentication entries to config.json for Artifactory repositories

set -u  # Exit on undefined variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREDENTIALS_FILE="${SCRIPT_DIR}/docker-credentials.txt"
DOCKER_CONFIG_FILE="${DOCKER_CONFIG:-${HOME}/.docker}/config.json"

# Simple logging
log() { echo "[$(date '+%H:%M:%S')] $1"; }
error() { log "ERROR: $1" >&2; }

# Exit gracefully on Ctrl+C and other termination signals
trap 'echo -e "\nInterrupted by user" >&2; exit 130' SIGINT SIGTERM

# Check prerequisites and load credentials
load_config() {
    # Check required tools
    for tool in curl jq base64; do
        command -v "$tool" >/dev/null 2>&1 || { 
            error "Required tool not found: $tool"
            exit 1
        }
    done

    # Check credentials file
    [[ -f "$CREDENTIALS_FILE" ]] || {
        error "Credentials file not found: $CREDENTIALS_FILE"
        echo "Create it by copying docker-credentials.txt.example"
        exit 1
    }
    
    # Check credentials file permissions
    if [[ -n "$(command -v stat 2>/dev/null)" ]]; then
        local perms=$(stat -c %a "$CREDENTIALS_FILE" 2>/dev/null || stat -f %Lp "$CREDENTIALS_FILE" 2>/dev/null)
        [[ "$perms" =~ ^[46]00$ ]] || {
            error "Warning: Credentials file has loose permissions: $CREDENTIALS_FILE"
            error "Consider: chmod 600 $CREDENTIALS_FILE"
        }
    fi

    # Load credentials more efficiently
    declare -g -A config=()
    local instance=""
    
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        
        # Trim whitespace
        key="${key%"${key##*[![:space:]]}"}"
        
        if [[ $key =~ ^\[(.*)\]$ ]]; then
            instance="${BASH_REMATCH[1]}"
            config["$instance,url"]=""
            config["$instance,user"]=""
            config["$instance,pass"]=""
        elif [[ -n "$instance" && -n "$value" ]]; then
            key="${key// /}"
            case "$key" in
                "ARTIFACTORY_URL") config["$instance,url"]="$value" ;;
                "USERNAME") config["$instance,user"]="$value" ;;
                "PASSWORD") config["$instance,pass"]="$value" ;;
            esac
        fi
    done < "$CREDENTIALS_FILE"
    
    # Extract instances in one pass
    declare -g -a INSTANCES=()
    for key in "${!config[@]}"; do
        [[ $key =~ ^([^,]+),url$ ]] && INSTANCES+=("${BASH_REMATCH[1]}")
    done
    
    [[ ${#INSTANCES[@]} -eq 0 ]] && {
        error "No valid instances found in credentials file"
        exit 1
    }
    
    log "Found ${#INSTANCES[@]} Artifactory instance(s)"
}

# Process repositories for a single Artifactory instance
process_repositories() {
    local instance="$1"
    local url="${config[$instance,url]}"
    local user="${config[$instance,user]}"
    local pass="${config[$instance,pass]}"
    local success=0
    local failed=0
    
    log "Processing $instance ($url)"
    
    # Get all repositories with type=docker
    local json
    json=$(curl -sS -f -u "$user:$pass" -H "Content-Type: application/json" \
        "${url%/artifactory}/artifactory/api/repositories" 2>/dev/null)
    
    if [[ $? -ne 0 ]]; then
        error "Failed to connect to Artifactory at $url"
        return 1
    fi
    
    # Parse repositories
    local repos=($(echo "$json" | jq -r '.[] | select(.packageType == "Docker") | .key' | sort -u))
    
    if [[ ${#repos[@]} -eq 0 ]]; then
        log "No Docker repositories found in $instance"
        return 1
    fi
    
    log "Found ${#repos[@]} Docker repositories in $instance:"
    printf '  - %s\n' "${repos[@]}"
    
    # Extract domain from URL
    [[ "$url" =~ ^https?://([^/]+) ]] || {
        error "Invalid URL format: $url"
        return 1
    }
    local domain="${BASH_REMATCH[1]%%/*}"
    
    # Ensure config directory exists
    mkdir -p "$(dirname "$DOCKER_CONFIG_FILE")"
    
    # Create or load config once
    local config_json
    if [[ -f "$DOCKER_CONFIG_FILE" ]]; then
        config_json=$(cat "$DOCKER_CONFIG_FILE")
        cp "$DOCKER_CONFIG_FILE" "$DOCKER_CONFIG_FILE.bak"
    else
        config_json='{"auths":{}}'
    fi
    
    # Update for all repositories in one go
    local temp=$(mktemp)
    
    for repo in "${repos[@]}"; do
        local registry="$repo.$domain"
        local auth=$(echo -n "$user:$pass" | base64 -w 0)
        
        log "Adding auth for $registry..."
        config_json=$(echo "$config_json" | jq --arg r "$registry" --arg a "$auth" \
            '.auths[$r] = {"auth": $a}')
            
        if [[ $? -eq 0 ]]; then
            log "✓ Added authentication for $registry"
            ((success++))
        else
            error "Failed to update config for $registry"
            ((failed++))
        fi
    done
    
    # Write updated config once
    echo "$config_json" > "$temp" && \
    mv "$temp" "$DOCKER_CONFIG_FILE" || {
        error "Failed to write config file"
        return 1
    }
    
    log "Instance $instance: $success successful, $failed failed"
    [[ $success -gt 0 ]]
}

# Main script
main() {
    log "Starting Artifactory Docker authentication setup"
    load_config
    
    local success=0
    local failed=0
    
    for instance in "${INSTANCES[@]}"; do
        echo "----------------------------------------"
        if process_repositories "$instance"; then
            ((success++))
        else
            ((failed++))
        fi
    done
    
    echo "----------------------------------------"
    log "Complete: $success instances succeeded, $failed failed"
    return $((failed > 0))
}

# Run main function
main "$@"
exit $?
