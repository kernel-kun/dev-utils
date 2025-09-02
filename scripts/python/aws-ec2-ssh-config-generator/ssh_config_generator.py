#!/usr/bin/env python3
"""
AWS ASG SSH Config Manager - Ultra Fast CLI Version

Minimal dependency version using AWS CLI for maximum performance.
No external dependencies required except AWS CLI.

Author: kernel-kun
Date: September 2, 2025
Version: 2.2.0 (Zero external dependencies)
"""

import argparse
import json
import os
import shutil
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Setup logging with minimal overhead."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load and minimally validate config file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        data = json.load(f)

    if "configs" not in data or not data["configs"]:
        raise ValueError("No configs found in configuration file")

    return data


def check_aws_cli() -> bool:
    """Check if AWS CLI is available and configured."""
    try:
        result = subprocess.run(
            ["aws", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            logger.debug(f"AWS CLI version: {result.stdout.strip()}")
            return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_asg_instances_cli(
    asg_name: str, region: str, profile: Optional[str] = None
) -> List[Dict[str, str]]:
    """Get ASG instances using AWS CLI."""
    try:
        # Build AWS CLI command for ASG
        cmd = [
            "aws",
            "autoscaling",
            "describe-auto-scaling-groups",
            "--auto-scaling-group-names",
            asg_name,
            "--region",
            region,
        ]

        if profile:
            cmd.extend(["--profile", profile])

        logger.debug(f"Getting ASG info: {asg_name}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error(f"AWS CLI error: {result.stderr}")
            return []

        asg_data = json.loads(result.stdout)
        auto_scaling_groups = asg_data.get("AutoScalingGroups", [])

        if not auto_scaling_groups:
            logger.warning(f"No ASG found: {asg_name}")
            return []

        # Extract instance IDs
        instances = auto_scaling_groups[0].get("Instances", [])
        instance_ids = [inst["InstanceId"] for inst in instances]

        if not instance_ids:
            logger.warning(f"No instances in ASG: {asg_name}")
            return []

        # Get instance details - batch them for efficiency
        cmd = ["aws", "ec2", "describe-instances", "--region", region]
        if profile:
            cmd.extend(["--profile", profile])
        cmd.extend(["--instance-ids"] + instance_ids)

        logger.debug(f"Getting details for {len(instance_ids)} instances")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.error(f"AWS CLI error for instances: {result.stderr}")
            return []

        ec2_data = json.loads(result.stdout)

        # Extract instance information
        instance_list = []
        for reservation in ec2_data.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                # Get instance name from tags
                name = instance["InstanceId"]
                for tag in instance.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break

                instance_list.append(
                    {
                        "id": instance["InstanceId"],
                        "ip": instance["PrivateIpAddress"],
                        "name": name,
                    }
                )

        logger.info(f"Found {len(instance_list)} instances in {asg_name}")
        return instance_list

    except subprocess.TimeoutExpired:
        logger.error(f"AWS CLI timeout for ASG: {asg_name}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AWS CLI output: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting ASG instances: {e}")
        return []


def parse_ssh_config_fast(ssh_path: Path) -> tuple:
    """Fast SSH config parsing using simple string operations."""
    if not ssh_path.exists():
        return "", set()

    with open(ssh_path, "r") as f:
        content = f.read()

    # Fast managed block detection
    managed_blocks = set()
    lines = content.split("\n")
    unmanaged_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for managed block start
        if line.startswith("# --- BEGIN ") and line.endswith(" ---"):
            block_name = line[12:-4]  # Remove prefix/suffix
            managed_blocks.add(block_name)

            # Skip to end of block
            while i < len(lines):
                if lines[i].startswith(f"# --- END {block_name} ---"):
                    break
                i += 1
        else:
            unmanaged_lines.append(line)

        i += 1

    unmanaged_content = "\n".join(unmanaged_lines)
    return unmanaged_content, managed_blocks


def generate_configs_fast(
    instances: List[Dict[str, str]], config: Dict[str, Any]
) -> List[str]:
    """Generate SSH config entries using fast string building."""
    configs = []
    prefix = config["prefix"]
    target = config["target_hosts"]
    jump_hosts = config["jump_hosts"]

    # Generate jump host configs
    jump_aliases = []
    for jump_host in jump_hosts:
        name = jump_host["name"]
        alias = f"{prefix}-jumphost-{name}"
        jump_aliases.append(alias)

        # Build jump host config
        jump_config = [
            f"# --- BEGIN {alias} ---",
            f"Host {alias}",
            f"    HostName {jump_host['hostname']}",
            f"    User {jump_host['user']}",
            f"    Port {jump_host['port']}",
            f"    IdentityFile {jump_host['identity_file']}",
            f"    ServerAliveInterval 240",
            f"    ServerAliveCountMax 43200",
            f"    StrictHostKeyChecking no",
            f"    ForwardAgent yes",
            f"    AddKeysToAgent yes",
        ]

        # Add custom options
        if "options" in jump_host:
            for key, value in jump_host["options"].items():
                jump_config.append(f"    {key} {value}")

        jump_config.append(f"# --- END {alias} ---")
        configs.append("\n".join(jump_config))

    # Generate instance configs
    proxy_jump = ",".join(jump_aliases)

    for instance in instances:
        host_alias = f"{prefix}-{instance['ip']}"
        block_name = f"{prefix}-{instance['id']}"

        instance_config = [
            f"# --- BEGIN {block_name} ---",
            f"Host {host_alias}",
            f"    HostName {instance['ip']}",
            f"    User {target['user']}",
            f"    Port {target['port']}",
            f"    IdentityFile {target['identity_file']}",
            f"    ProxyJump {proxy_jump}",
            f"    ServerAliveInterval 240",
            f"    ServerAliveCountMax 43200",
            f"    Compression yes",
            f"    ForwardAgent yes",
            f"    AddKeysToAgent yes",
        ]

        # Add target options
        if "options" in target:
            for key, value in target["options"].items():
                instance_config.append(f"    {key} {value}")

        instance_config.append(f"# --- END {block_name} ---")
        configs.append("\n".join(instance_config))

    return configs


def write_ssh_config_fast(
    ssh_path: Path,
    unmanaged_content: str,
    new_configs: List[str],
    dry_run: bool = False,
    backup: bool = True,
) -> None:
    """Fast SSH config writing."""
    # Create backup if needed
    if backup and ssh_path.exists() and not dry_run:
        backup_dir = ssh_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = backup_dir / f"config.{timestamp}.bak"
        shutil.copy2(ssh_path, backup_path)
        logger.info(f"Backup: {backup_path}")

    # Build content
    parts = []

    # Add global settings if needed
    if "# Global SSH settings" not in unmanaged_content:
        global_settings = [
            "# Global SSH settings - Managed by asg-ssh-config-manager",
            "Host *",
            "    ServerAliveInterval 60",
            "    ForwardAgent yes",
            "    AddKeysToAgent yes",
            "    ControlPath /tmp/master-%h.socket",
            "    ControlMaster auto",
            "    ControlPersist yes",
            "    Compression yes",
            "    StrictHostKeyChecking no",
            "",
        ]
        parts.extend(global_settings)

    # Add unmanaged content
    if unmanaged_content.strip():
        parts.append(unmanaged_content.rstrip())
        parts.append("")

    # Add new configs
    if new_configs:
        parts.append("# ASG SSH configurations - managed by asg-ssh-config-manager")
        parts.append(f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        parts.append("")

        for config in new_configs:
            parts.append(config)
            parts.append("")

    final_content = "\n".join(parts)

    if dry_run:
        logger.info("DRY RUN - would update SSH config")
        lines = final_content.split("\n")
        preview_lines = min(20, len(lines))
        print("\n".join(lines[:preview_lines]))
        if len(lines) > preview_lines:
            print(f"... ({len(lines) - preview_lines} more lines)")
    else:
        # Ensure directory exists
        ssh_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        temp_path = ssh_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            f.write(final_content)

        temp_path.replace(ssh_path)
        ssh_path.chmod(0o600)
        logger.info(f"Updated: {ssh_path}")


def process_asg(config: Dict[str, Any]) -> List[str]:
    """Process a single ASG configuration."""
    name = config["name"]
    asg_name = config["asg_name"]
    aws_config = config["aws"]

    logger.info(f"Processing {name} (ASG: {asg_name})")

    # Get instances using AWS CLI
    instances = get_asg_instances_cli(
        asg_name, aws_config["region"], aws_config.get("profile")
    )

    if not instances:
        return []

    # Generate configs
    return generate_configs_fast(instances, config)


def list_hosts(ssh_path: Path, prefix_filter: Optional[str] = None) -> None:
    """List managed SSH hosts."""
    if not ssh_path.exists():
        print(f"SSH config not found: {ssh_path}")
        return

    with open(ssh_path, "r") as f:
        content = f.read()

    print(f"\nManaged SSH hosts in {ssh_path}:")
    print("-" * 80)
    print(f"{'HOSTNAME':<40} {'IP ADDRESS':<15} {'USER':<15}")
    print(f"{'--------':<40} {'----------':<15} {'----':<15}")

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("# --- BEGIN ") and line.endswith(" ---"):
            block_name = line[12:-4]

            # Apply prefix filter
            if prefix_filter and not block_name.startswith(prefix_filter):
                # Skip to end of block
                while i < len(lines) and not lines[i].startswith(
                    f"# --- END {block_name} ---"
                ):
                    i += 1
                i += 1
                continue

            # Parse block for host info
            hostname = ip = user = ""
            i += 1

            while i < len(lines) and not lines[i].startswith("# --- END"):
                line = lines[i].strip()
                if line.startswith("Host ") and not line.startswith("HostName"):
                    hostname = line.split()[1]
                elif line.startswith("HostName "):
                    ip = line.split()[1]
                elif line.startswith("User "):
                    user = line.split()[1]
                i += 1

            # Only show instance entries (not jump hosts)
            if hostname and not hostname.endswith("-jumphost"):
                print(f"{hostname:<40} {ip:<15} {user:<15}")

        i += 1

    print()


def main():
    """Main entry point - no external dependencies except AWS CLI."""
    parser = argparse.ArgumentParser(
        description="AWS ASG SSH Config Manager - Ultra Fast Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -c config.json                       # Update SSH config
  %(prog)s -c config.json --dry-run             # Preview changes
  %(prog)s -c config.json --asg prod-cluster    # Process specific ASG
  %(prog)s -c config.json --list                # List managed hosts
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        default="./asg-ssh-config.json",
        help="Configuration file path (default: ./asg-ssh-config.json)",
    )
    parser.add_argument(
        "-o", "--output", help="SSH config output file (overrides config setting)"
    )
    parser.add_argument(
        "-a", "--asg", help="Process only the specified ASG configuration"
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-l", "--list", action="store_true", help="List all managed SSH hosts"
    )
    parser.add_argument(
        "-p", "--prefix", help="Filter hosts by prefix (use with --list)"
    )
    parser.add_argument("--version", action="version", version="%(prog)s 2.2.0")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    try:
        # Check AWS CLI availability
        if not check_aws_cli():
            logger.error(
                "AWS CLI not found. Please install AWS CLI and configure credentials."
            )
            logger.info(
                "Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
            )
            sys.exit(1)

        # Load configuration
        config_path = Path(args.config)
        config_data = load_config(config_path)

        # Determine SSH config path
        if args.output:
            ssh_path = Path(args.output)
        else:
            default_path = config_data.get("settings", {}).get(
                "ssh_config_path", "~/.ssh/config"
            )
            ssh_path = Path(os.path.expanduser(default_path))

        # Handle list hosts
        if args.list:
            list_hosts(ssh_path, args.prefix)
            return

        if args.dry_run:
            logger.info("=== DRY RUN MODE ===")

        # Parse existing SSH config
        unmanaged_content, existing_blocks = parse_ssh_config_fast(ssh_path)

        # Process configurations
        all_configs = []
        backup_enabled = config_data.get("settings", {}).get("backup", True)

        for config in config_data["configs"]:
            if args.asg and config["name"] != args.asg:
                continue

            try:
                new_configs = process_asg(config)
                all_configs.extend(new_configs)
            except Exception as e:
                logger.error(f"Failed to process {config['name']}: {e}")
                continue

        # Write updated config
        write_ssh_config_fast(
            ssh_path, unmanaged_content, all_configs, args.dry_run, backup_enabled
        )

        if not args.dry_run:
            logger.info("✓ Completed successfully")

    except KeyboardInterrupt:
        logger.info("Cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
