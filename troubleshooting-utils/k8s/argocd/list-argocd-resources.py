#!/usr/bin/env python3
"""
ArgoCD Resource Lister

List and filter ArgoCD applications and resources by sync/health status.

Usage:
    ./list-argocd-resources.py [parent-app] [options]

Examples:
    # List all child apps (backward compatible)
    ./list-argocd-resources.py my-parent-app

    # Filter by sync status
    ./list-argocd-resources.py my-parent-app --sync-status OutOfSync

    # Filter by health status
    ./list-argocd-resources.py my-parent-app --health-status Degraded

    # Combined filters
    ./list-argocd-resources.py my-parent-app --sync-status Synced --health-status Healthy

    # Recursive discovery
    ./list-argocd-resources.py my-parent-app --recursive

    # Output formats
    ./list-argocd-resources.py my-parent-app --output table  # Human-readable
    ./list-argocd-resources.py my-parent-app --output json   # Machine-parseable
    ./list-argocd-resources.py my-parent-app --output plain  # For piping (default)
"""

import sys
import json
import asyncio
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from urllib.parse import quote as urlquote

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Error: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# Valid status values
VALID_SYNC_STATUSES = {'Synced', 'OutOfSync', 'Unknown'}
VALID_HEALTH_STATUSES = {'Healthy', 'Progressing', 'Degraded', 'Suspended', 'Missing', 'Unknown'}


@dataclass
class ArgocdConnection:
    server: str
    token: str


def load_argocd_auth(host: Optional[str] = None) -> ArgocdConnection:
    config_path = Path.home() / ".config" / "argocd" / "config"
    if not config_path.exists():
        print(f"Error: ArgoCD config not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if host:
        server = host.removeprefix("https://").removeprefix("http://").rstrip("/")
    else:
        server = config.get("current-context")
        if not server:
            print("Error: No --host given and no current-context in argocd config", file=sys.stderr)
            sys.exit(1)

    users = config.get("users", [])
    token = None
    for user in users:
        if user.get("name") == server:
            token = user.get("auth-token")
            break

    if not token:
        available = [u.get("name", "?") for u in users]
        print(f"Error: No auth-token for '{server}'. Available: {available}", file=sys.stderr)
        print(f"Run: argocd login {server} --sso", file=sys.stderr)
        sys.exit(1)

    return ArgocdConnection(server=server, token=token)


def parse_arguments() -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description='List and filter ArgoCD applications by sync/health status',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s my-parent-app
  %(prog)s my-parent-app --sync-status OutOfSync
  %(prog)s my-parent-app --health-status Degraded
  %(prog)s my-parent-app --sync-status Synced --health-status Healthy
  %(prog)s my-parent-app --recursive --output table
  %(prog)s my-parent-app --output json | jq '.'
  %(prog)s my-parent-app --sync-status OutOfSync | xargs ./cleanup-argocd-apps.sh
        """
    )

    parser.add_argument(
        'parent_app',
        nargs='?',
        default='csusw2-d-ones-test-cluster-addons-parent',
        help='Parent ArgoCD application name (default: csusw2-d-ones-test-cluster-addons-parent)'
    )

    parser.add_argument(
        '--sync-status',
        type=str,
        metavar='STATUS',
        help=f'Filter by sync status (comma-separated). Valid: {", ".join(sorted(VALID_SYNC_STATUSES))}'
    )

    parser.add_argument(
        '--health-status',
        type=str,
        metavar='STATUS',
        help=f'Filter by health status (comma-separated). Valid: {", ".join(sorted(VALID_HEALTH_STATUSES))}'
    )

    parser.add_argument(
        '--recursive',
        action='store_true',
        help='Recursively discover and list nested child applications (unlimited depth)'
    )

    parser.add_argument(
        '--depth',
        type=int,
        metavar='N',
        help='Limit recursion depth (0=parent only, 1=parent+children, 2=parent+children+grandchildren, etc.). Implies --recursive.'
    )

    parser.add_argument(
        '--output',
        choices=['table', 'plain', 'json'],
        default='plain',
        help='Output format: table (human-readable), plain (names only, for piping), json (structured data). Default: plain'
    )

    parser.add_argument(
        '--namespace',
        default='argocd',
        help='ArgoCD namespace (default: argocd)'
    )

    parser.add_argument(
        '--argocd-only',
        action='store_true',
        help='Only show ArgoCD-specific resources (Application, ApplicationSet, AppProject)'
    )

    parser.add_argument(
        '--host',
        type=str,
        metavar='SERVER',
        help='ArgoCD server hostname (default: current-context from ~/.config/argocd/config)'
    )

    parser.add_argument(
        '--no-verify-ssl',
        action='store_true',
        help='Skip SSL certificate verification'
    )

    parser.add_argument(
        '--concurrency',
        type=int,
        default=10,
        metavar='N',
        help='Max concurrent API requests per BFS level (default: 10)'
    )

    args = parser.parse_args()

    # Validate sync status values
    if args.sync_status:
        sync_statuses = [s.strip() for s in args.sync_status.split(',')]
        invalid_sync = set(sync_statuses) - VALID_SYNC_STATUSES
        if invalid_sync:
            parser.error(
                f"Invalid sync status values: {', '.join(invalid_sync)}\n"
                f"Valid values: {', '.join(sorted(VALID_SYNC_STATUSES))}"
            )
        args.sync_status = sync_statuses
    else:
        args.sync_status = []

    # Validate health status values
    if args.health_status:
        health_statuses = [s.strip() for s in args.health_status.split(',')]
        invalid_health = set(health_statuses) - VALID_HEALTH_STATUSES
        if invalid_health:
            parser.error(
                f"Invalid health status values: {', '.join(invalid_health)}\n"
                f"Valid values: {', '.join(sorted(VALID_HEALTH_STATUSES))}"
            )
        args.health_status = health_statuses
    else:
        args.health_status = []

    # Handle depth flag
    if args.depth is not None:
        if args.depth < 0:
            parser.error("Depth must be non-negative")
        # --depth implies --recursive
        args.recursive = True

    return args


class ArgocdApiClient:
    def __init__(self, conn: ArgocdConnection, verify_ssl: bool = True, concurrency: int = 10):
        self.conn = conn
        self.base_url = f"https://{conn.server}"
        self.headers = {"Authorization": f"Bearer {conn.token}"}
        self.verify_ssl = verify_ssl
        self.sem = asyncio.Semaphore(concurrency)
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            verify=self.verify_ssl,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str) -> Optional[Dict[str, Any]]:
        async with self.sem:
            try:
                resp = await self._client.get(path)
            except httpx.ConnectError as e:
                print(f"Connection error: {e}", file=sys.stderr)
                return None
            except httpx.TimeoutException:
                print(f"Timeout: GET {path}", file=sys.stderr)
                return None

        if resp.status_code == 401 or resp.status_code == 403:
            print(f"Auth error ({resp.status_code}). Run: argocd login {self.conn.server} --sso", file=sys.stderr)
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            print(f"HTTP {resp.status_code}: GET {path}", file=sys.stderr)
            return None
        return resp.json()

    async def get_application(self, name: str, ns: str = "argocd") -> Optional[Dict]:
        return await self._get(f"/api/v1/applications/{urlquote(name)}?appNamespace={urlquote(ns)}")

    async def get_resource_tree(self, name: str, ns: str = "argocd") -> Optional[Dict]:
        return await self._get(f"/api/v1/applications/{urlquote(name)}/resource-tree?appNamespace={urlquote(ns)}")

    async def fetch_app_with_resources(self, name: str, ns: str = "argocd") -> Optional[Dict]:
        app_data, tree_data = await asyncio.gather(
            self.get_application(name, ns),
            self.get_resource_tree(name, ns),
            return_exceptions=True,
        )
        if isinstance(app_data, Exception) or app_data is None:
            if not isinstance(app_data, Exception):
                print(f"Warning: Could not fetch application '{name}', skipping...", file=sys.stderr)
            return None

        sync_lookup = {}
        for res in app_data.get("status", {}).get("resources", []):
            key = (res.get("group", ""), res.get("kind", ""), res.get("namespace", ""), res.get("name", ""))
            sync_lookup[key] = res.get("status", "Unknown")

        resources = []
        if not isinstance(tree_data, Exception) and tree_data is not None:
            for node in tree_data.get("nodes", []):
                group = node.get("group", "")
                kind = node.get("kind", "")
                node_ns = node.get("namespace", "")
                rname = node.get("name", "")
                health = node.get("health", {}).get("status", "Unknown") if isinstance(node.get("health"), dict) else "Unknown"
                sync = sync_lookup.get((group, kind, node_ns, rname), "Unknown")
                version = node.get("version", "")
                if rname and kind:
                    resources.append({
                        "name": rname, "kind": kind, "group": group,
                        "version": version, "namespace": node_ns,
                        "parentApp": name,
                        "syncStatus": sync, "healthStatus": health,
                    })
        else:
            for res in app_data.get("status", {}).get("resources", []):
                kind = res.get("kind", "")
                rname = res.get("name", "")
                if rname and kind:
                    health = res.get("health", {}).get("status", "Unknown") if isinstance(res.get("health"), dict) else "Unknown"
                    resources.append({
                        "name": rname, "kind": kind, "group": res.get("group", ""),
                        "version": res.get("version", ""), "namespace": res.get("namespace", ""),
                        "parentApp": name,
                        "syncStatus": res.get("status", "Unknown"), "healthStatus": health,
                    })

        return {
            "name": name,
            "syncStatus": extract_sync_status(app_data),
            "healthStatus": extract_health_status(app_data),
            "resources": resources,
        }


def extract_sync_status(app_data: Dict[str, Any]) -> str:
    """
    Extract sync status from application data, defaulting to 'Unknown' if missing.

    Args:
        app_data: ArgoCD application data dict

    Returns:
        Sync status string
    """
    try:
        return app_data.get('status', {}).get('sync', {}).get('status', 'Unknown')
    except (KeyError, TypeError, AttributeError):
        return 'Unknown'


def extract_health_status(app_data: Dict[str, Any]) -> str:
    """
    Extract health status from application data, defaulting to 'Unknown' if missing.

    Args:
        app_data: ArgoCD application data dict

    Returns:
        Health status string
    """
    try:
        return app_data.get('status', {}).get('health', {}).get('status', 'Unknown')
    except (KeyError, TypeError, AttributeError):
        return 'Unknown'




def is_argocd_application(resource: Dict[str, Any]) -> bool:
    """
    Check if a resource is an ArgoCD Application or Application-like resource.

    Args:
        resource: Resource dict

    Returns:
        True if resource is an Application (native ArgoCD or Crossplane-managed)
    """
    kind = resource.get('kind', '')
    group = resource.get('group', '')

    # Native ArgoCD Application
    if kind == 'Application' and group == 'argoproj.io':
        return True

    # Crossplane Application claim (creates ArgoCD Applications)
    if kind == 'Application' and 'argocd' in group.lower():
        return True

    # ApplicationSet also can create Applications
    if kind == 'ApplicationSet' and group == 'argoproj.io':
        return True

    return False


async def discover_resources_async(
    client: ArgocdApiClient,
    parent_app: str,
    app_namespace: str,
    recursive: bool,
    sync_statuses: List[str],
    health_statuses: List[str],
    argocd_only: bool,
    max_depth: Optional[int] = None,
) -> List[Dict[str, Any]]:
    all_resources: List[Dict[str, Any]] = []
    visited: Set[str] = set()
    current_level = [(parent_app, 0)]

    while current_level:
        to_fetch = [(name, depth) for name, depth in current_level if name not in visited]
        if not to_fetch:
            break
        for name, _ in to_fetch:
            visited.add(name)

        results = await asyncio.gather(
            *(client.fetch_app_with_resources(name, app_namespace) for name, _ in to_fetch),
            return_exceptions=True,
        )

        next_level: List[Tuple[str, int]] = []
        for (app_name, depth), result in zip(to_fetch, results):
            if isinstance(result, Exception) or result is None:
                continue
            for resource in result["resources"]:
                if recursive and is_argocd_application(resource):
                    child_name = resource["name"]
                    next_depth = depth + 1
                    if child_name not in visited:
                        if max_depth is None or next_depth <= max_depth:
                            next_level.append((child_name, next_depth))

                if argocd_only:
                    group = resource.get("group", "")
                    kind = resource.get("kind", "")
                    if not (group == "argoproj.io" and kind in ("Application", "ApplicationSet", "AppProject")):
                        continue

                entry = {
                    "name": resource["name"],
                    "kind": resource["kind"],
                    "group": resource.get("group", ""),
                    "version": resource.get("version", ""),
                    "namespace": resource["namespace"],
                    "parentApp": resource.get("parentApp", ""),
                    "syncStatus": resource.get("syncStatus", "Unknown"),
                    "healthStatus": resource.get("healthStatus", "Unknown"),
                }
                passes = (
                    (not sync_statuses or entry["syncStatus"] in sync_statuses)
                    and (not health_statuses or entry["healthStatus"] in health_statuses)
                )
                if passes:
                    all_resources.append(entry)

        current_level = next_level

    return all_resources


def format_plain(resources: List[Dict[str, Any]]) -> str:
    """
    Format resources as plain text (newline-delimited names).

    Args:
        resources: List of resource dicts

    Returns:
        Formatted string
    """
    return '\n'.join(r['name'] for r in resources)


def format_table(resources: List[Dict[str, Any]]) -> str:
    """
    Format resources as human-readable table.

    Args:
        resources: List of resource dicts

    Returns:
        Formatted table string
    """
    if not resources:
        return "NAME                KIND           NAMESPACE      SYNC STATUS    HEALTH STATUS\n" + \
               "-" * 80 + "\n" + \
               "No resources found"

    # Calculate column widths
    name_width = max(len(r['name']) for r in resources)
    name_width = max(name_width, len('NAME'))
    kind_width = max(len(r['kind']) for r in resources)
    kind_width = max(kind_width, len('KIND'))
    namespace_width = max(len(r.get('namespace', '')) for r in resources)
    namespace_width = max(namespace_width, len('NAMESPACE'))
    sync_width = max(len(r['syncStatus']) for r in resources)
    sync_width = max(sync_width, len('SYNC STATUS'))
    health_width = max(len(r['healthStatus']) for r in resources)
    health_width = max(health_width, len('HEALTH STATUS'))

    # Build table
    lines = []
    header = f"{'NAME':<{name_width}}  {'KIND':<{kind_width}}  {'NAMESPACE':<{namespace_width}}  {'SYNC STATUS':<{sync_width}}  {'HEALTH STATUS':<{health_width}}"
    lines.append(header)
    lines.append('-' * len(header))

    for resource in resources:
        namespace = resource.get('namespace', '')
        line = f"{resource['name']:<{name_width}}  {resource['kind']:<{kind_width}}  {namespace:<{namespace_width}}  {resource['syncStatus']:<{sync_width}}  {resource['healthStatus']:<{health_width}}"
        lines.append(line)

    return '\n'.join(lines)


def format_json(resources: List[Dict[str, Any]]) -> str:
    """
    Format resources as JSON array.

    Args:
        resources: List of resource dicts

    Returns:
        JSON string
    """
    return json.dumps(resources, indent=2)


def main():
    try:
        args = parse_arguments()
        conn = load_argocd_auth(host=args.host)

        async def _run():
            async with ArgocdApiClient(conn, verify_ssl=not args.no_verify_ssl, concurrency=args.concurrency) as client:
                return await discover_resources_async(
                    client=client,
                    parent_app=args.parent_app,
                    app_namespace=args.namespace,
                    recursive=args.recursive,
                    sync_statuses=args.sync_status,
                    health_statuses=args.health_status,
                    argocd_only=args.argocd_only,
                    max_depth=args.depth if args.depth is not None else None,
                )

        resources = asyncio.run(_run())

        if args.output == 'plain':
            output = format_plain(resources)
        elif args.output == 'table':
            output = format_table(resources)
        elif args.output == 'json':
            output = format_json(resources)
        else:
            sys.exit(1)

        if output:
            print(output)

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
