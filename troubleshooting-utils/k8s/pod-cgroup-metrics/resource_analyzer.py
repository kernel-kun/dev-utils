#!/usr/bin/env python3
"""
Simple Resource Usage Analyzer
Focuses on CPU/Memory limits, usage patterns, and clear visualizations
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
import sys
from pathlib import Path

def convert_cpu_to_millicores(cpu_usage_usec, interval_seconds=24):
    """Convert cumulative CPU microseconds to millicores rate
    
    Formula: 
    - delta_usec = change in cumulative CPU time (microseconds)
    - rate = delta_usec / interval_seconds (microseconds per second)
    - millicores = rate / 1000 (since 1 core = 1,000,000 μs/s, 1 millicore = 1,000 μs/s)
    """
    if len(cpu_usage_usec) < 2:
        return [0] * len(cpu_usage_usec)
    
    rates = [0]  # First value has no previous reference
    for i in range(1, len(cpu_usage_usec)):
        # Calculate delta usage over the interval
        delta_usec = max(0, cpu_usage_usec[i] - cpu_usage_usec[i-1])
        # Convert to millicores: (delta_usec / interval_seconds) / 1000
        # This gives us: microseconds_per_second / 1000 = millicores
        millicores = (delta_usec / interval_seconds) / 1000.0
        rates.append(millicores)
    
    return rates

def convert_memory_to_mb(memory_bytes):
    """Convert memory from bytes to MB"""
    return [bytes_val / (1024 * 1024) for bytes_val in memory_bytes]

def convert_memory_to_gb(memory_bytes):
    """Convert memory from bytes to GB"""
    return [bytes_val / (1024 * 1024 * 1024) for bytes_val in memory_bytes]

def load_and_process_data(csv_file):
    """Load CSV and calculate derived metrics"""
    try:
        df = pd.read_csv(csv_file)
        print(f"✅ Loaded {len(df)} data points")
        
        # Convert timestamps and create time column
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['time_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
        
        # Auto-detect the monitoring interval from timestamps
        if len(df) > 1:
            interval_seconds = (df['timestamp'].iloc[1] - df['timestamp'].iloc[0]).total_seconds()
            print(f"📊 Detected monitoring interval: {interval_seconds:.0f} seconds")
        else:
            interval_seconds = 24  # Default fallback
          # Calculate CPU rates (millicores) from cumulative usage
        df['runner_cpu_millicores'] = convert_cpu_to_millicores(
            df['runner_cpu_usage_usec'].tolist(), interval_seconds)
        df['dind_cpu_millicores'] = convert_cpu_to_millicores(
            df['dind_cpu_usage_usec'].tolist(), interval_seconds)
        
        # Debug: Show some sample conversions
        if len(df) > 1:
            runner_delta = df['runner_cpu_usage_usec'].iloc[1] - df['runner_cpu_usage_usec'].iloc[0]
            runner_millicores = df['runner_cpu_millicores'].iloc[1]
            print(f"🔍 Sample conversion - Runner:")
            print(f"   CPU delta: {runner_delta:,} μs over {interval_seconds:.0f}s")
            print(f"   Calculated: {runner_millicores:.0f} millicores ({runner_millicores/1000:.2f} CPU cores)")
            
            dind_delta = df['dind_cpu_usage_usec'].iloc[1] - df['dind_cpu_usage_usec'].iloc[0]
            dind_millicores = df['dind_cpu_millicores'].iloc[1]
            print(f"   DinD delta: {dind_delta:,} μs over {interval_seconds:.0f}s")
            print(f"   Calculated: {dind_millicores:.0f} millicores ({dind_millicores/1000:.2f} CPU cores)")
        
        
        # Convert memory to MB and GB
        df['runner_memory_mb'] = convert_memory_to_mb(df['runner_memory_current'])
        df['dind_memory_mb'] = convert_memory_to_mb(df['dind_memory_current'])
        df['runner_memory_gb'] = convert_memory_to_gb(df['runner_memory_current'])
        df['dind_memory_gb'] = convert_memory_to_gb(df['dind_memory_current'])
        
        # Convert memory limits (handle 'max' values)
        def safe_convert_limit(limit_val):
            if limit_val == 'max' or pd.isna(limit_val):
                return 8  # Default 8GB limit for visualization
            return limit_val / (1024 * 1024 * 1024)  # Convert to GB
        
        df['runner_memory_limit_gb'] = df['runner_memory_max'].apply(safe_convert_limit)
        df['dind_memory_limit_gb'] = df['dind_memory_max'].apply(safe_convert_limit)
        
        # Calculate CPU throttling rates (percentage)
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
        
        return df
        
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        sys.exit(1)

def create_resource_overview(df, output_file=None):
    """Create a comprehensive but simple resource overview"""
    
    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle('Container Resource Usage Overview', fontsize=16, fontweight='bold')
    
    # Color scheme
    colors = {'runner': '#2E86AB', 'dind': '#A23B72'}
    
    # 1. CPU Usage (millicores) - Top Left
    ax1 = axes[0, 0]
    ax1.plot(df['time_minutes'], df['runner_cpu_millicores'], 
             color=colors['runner'], label='Runner', linewidth=2, alpha=0.8)
    ax1.plot(df['time_minutes'], df['dind_cpu_millicores'], 
             color=colors['dind'], label='DinD', linewidth=2, alpha=0.8)
    
    # Add CPU limit reference lines (assuming no hard CPU limits, show reasonable thresholds)
    ax1.axhline(y=1000, color='orange', linestyle='--', alpha=0.5, label='1 CPU (1000m)')
    ax1.axhline(y=2000, color='red', linestyle='--', alpha=0.5, label='2 CPU (2000m)')
    
    ax1.set_title('CPU Usage Over Time', fontweight='bold', fontsize=12)
    ax1.set_xlabel('Time (minutes)')
    ax1.set_ylabel('CPU Usage (millicores)')
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(bottom=0)
    
    # 2. Memory Usage with Limits - Top Right
    ax2 = axes[0, 1]
    ax2.plot(df['time_minutes'], df['runner_memory_gb'], 
             color=colors['runner'], label='Runner Usage', linewidth=2, alpha=0.8)
    ax2.plot(df['time_minutes'], df['dind_memory_gb'], 
             color=colors['dind'], label='DinD Usage', linewidth=2, alpha=0.8)
    
    # Add memory limit lines
    runner_limit = df['runner_memory_limit_gb'].iloc[0]
    dind_limit = df['dind_memory_limit_gb'].iloc[0]
    ax2.axhline(y=runner_limit, color=colors['runner'], linestyle='--', alpha=0.6, 
                label=f'Runner Limit ({runner_limit:.1f}GB)')
    ax2.axhline(y=dind_limit, color=colors['dind'], linestyle='--', alpha=0.6, 
                label=f'DinD Limit ({dind_limit:.1f}GB)')
    
    ax2.set_title('Memory Usage vs Limits', fontweight='bold', fontsize=12)
    ax2.set_xlabel('Time (minutes)')
    ax2.set_ylabel('Memory Usage (GB)')
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(bottom=0)
    
    # 3. CPU Throttling Events - Bottom Left
    ax3 = axes[1, 0]
    if df['runner_cpu_throttling_pct'].max() > 0 or df['dind_cpu_throttling_pct'].max() > 0:
        ax3.plot(df['time_minutes'], df['runner_cpu_throttling_pct'], 
                 color=colors['runner'], label='Runner', linewidth=2, alpha=0.8)
        ax3.plot(df['time_minutes'], df['dind_cpu_throttling_pct'], 
                 color=colors['dind'], label='DinD', linewidth=2, alpha=0.8)
        ax3.set_ylabel('Throttling Rate (%)')
    else:
        ax3.text(0.5, 0.5, 'No CPU Throttling Detected\n(No CPU limits set)', 
                 horizontalalignment='center', verticalalignment='center', 
                 transform=ax3.transAxes, fontsize=12, alpha=0.7)
        ax3.set_ylabel('Throttling Rate (%)')
        ax3.set_ylim(0, 1)
    
    ax3.set_title('CPU Throttling Events', fontweight='bold', fontsize=12)
    ax3.set_xlabel('Time (minutes)')
    ax3.legend(fontsize=10)
    ax3.grid(True, alpha=0.3)
    
    # 4. Process Count and System Load - Bottom Right
    ax4 = axes[1, 1]
    # Use secondary y-axis for different scales
    ax4_twin = ax4.twinx()
    
    # Plot process counts
    line1 = ax4.plot(df['time_minutes'], df['runner_pids_current'], 
                     color=colors['runner'], label='Runner PIDs', linewidth=2, alpha=0.8)
    line2 = ax4.plot(df['time_minutes'], df['dind_pids_current'], 
                     color=colors['dind'], label='DinD PIDs', linewidth=2, alpha=0.8)
    
    # Plot system load on secondary axis
    line3 = ax4_twin.plot(df['time_minutes'], df['runner_load_1min'], 
                          color='gray', linestyle=':', label='System Load', linewidth=2, alpha=0.6)
    
    ax4.set_title('Process Count & System Load', fontweight='bold', fontsize=12)
    ax4.set_xlabel('Time (minutes)')
    ax4.set_ylabel('Process Count (PIDs)', color='black')
    ax4_twin.set_ylabel('System Load (1min avg)', color='gray')
    
    # Combine legends
    lines = line1 + line2 + line3
    labels = [l.get_label() for l in lines]
    ax4.legend(lines, labels, fontsize=10, loc='upper left')
    
    ax4.grid(True, alpha=0.3)
    ax4.set_ylim(bottom=0)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Resource overview saved to: {output_file}")
    else:
        plt.show()
    
    return fig

def print_resource_summary(df):
    """Print a summary of resource usage patterns"""
    print("\n" + "="*70)
    print("📊 RESOURCE USAGE SUMMARY")
    print("="*70)
    
    # Time range
    duration_minutes = df['time_minutes'].max()
    print(f"⏱️  Monitoring Duration: {duration_minutes:.1f} minutes")
    print(f"📈 Data Points Collected: {len(df)}")
    
    # CPU Analysis
    print(f"\n🖥️  CPU USAGE ANALYSIS:")
    runner_cpu_avg = df['runner_cpu_millicores'].mean()
    runner_cpu_max = df['runner_cpu_millicores'].max()
    dind_cpu_avg = df['dind_cpu_millicores'].mean()
    dind_cpu_max = df['dind_cpu_millicores'].max()
    
    print(f"   Runner Container:")
    print(f"     Average: {runner_cpu_avg:.0f} millicores ({runner_cpu_avg/1000:.2f} CPU cores)")
    print(f"     Peak:    {runner_cpu_max:.0f} millicores ({runner_cpu_max/1000:.2f} CPU cores)")
    print(f"   DinD Container:")
    print(f"     Average: {dind_cpu_avg:.0f} millicores ({dind_cpu_avg/1000:.2f} CPU cores)")
    print(f"     Peak:    {dind_cpu_max:.0f} millicores ({dind_cpu_max/1000:.2f} CPU cores)")
    
    # Memory Analysis
    print(f"\n💾 MEMORY USAGE ANALYSIS:")
    runner_mem_avg = df['runner_memory_gb'].mean()
    runner_mem_max = df['runner_memory_gb'].max()
    runner_mem_limit = df['runner_memory_limit_gb'].iloc[0]
    dind_mem_avg = df['dind_memory_gb'].mean()
    dind_mem_max = df['dind_memory_gb'].max()
    dind_mem_limit = df['dind_memory_limit_gb'].iloc[0]
    
    print(f"   Runner Container:")
    print(f"     Average: {runner_mem_avg:.2f} GB ({runner_mem_avg/runner_mem_limit*100:.1f}% of limit)")
    print(f"     Peak:    {runner_mem_max:.2f} GB ({runner_mem_max/runner_mem_limit*100:.1f}% of limit)")
    print(f"     Limit:   {runner_mem_limit:.1f} GB")
    print(f"   DinD Container:")
    print(f"     Average: {dind_mem_avg:.2f} GB ({dind_mem_avg/dind_mem_limit*100:.1f}% of limit)")
    print(f"     Peak:    {dind_mem_max:.2f} GB ({dind_mem_max/dind_mem_limit*100:.1f}% of limit)")
    print(f"     Limit:   {dind_mem_limit:.1f} GB")
    
    # Process Analysis
    print(f"\n🔧 PROCESS & SYSTEM ANALYSIS:")
    runner_pids_avg = df['runner_pids_current'].mean()
    runner_pids_max = df['runner_pids_current'].max()
    dind_pids_avg = df['dind_pids_current'].mean()
    dind_pids_max = df['dind_pids_current'].max()
    load_avg = df['runner_load_1min'].mean()
    load_max = df['runner_load_1min'].max()
    
    print(f"   Runner Processes: Avg {runner_pids_avg:.0f}, Peak {runner_pids_max:.0f}")
    print(f"   DinD Processes:   Avg {dind_pids_avg:.0f}, Peak {dind_pids_max:.0f}")
    print(f"   System Load:      Avg {load_avg:.2f}, Peak {load_max:.2f}")
    
    # Throttling Analysis
    runner_throttling = df['runner_cpu_throttling_pct'].max()
    dind_throttling = df['dind_cpu_throttling_pct'].max()
    
    print(f"\n⚠️  CPU THROTTLING ANALYSIS:")
    if runner_throttling > 0 or dind_throttling > 0:
        print(f"   Runner Max Throttling: {runner_throttling:.1f}%")
        print(f"   DinD Max Throttling:   {dind_throttling:.1f}%")
    else:
        print(f"   ✅ No CPU throttling detected (no CPU limits configured)")
    
    # Resource efficiency insights
    print(f"\n💡 INSIGHTS:")
    if runner_cpu_max > 2000:
        print(f"   🔥 Runner container used significant CPU ({runner_cpu_max/1000:.1f} cores peak)")
    if dind_cpu_max > 2000:
        print(f"   🔥 DinD container used significant CPU ({dind_cpu_max/1000:.1f} cores peak)")
    if runner_mem_max/runner_mem_limit > 0.8:
        print(f"   🔥 Runner memory usage reached {runner_mem_max/runner_mem_limit*100:.1f}% of limit")
    if dind_mem_max/dind_mem_limit > 0.8:
        print(f"   🔥 DinD memory usage reached {dind_mem_max/dind_mem_limit*100:.1f}% of limit")
    if load_max > 4:
        print(f"   ⚠️  High system load detected (peak: {load_max:.1f})")

def main():
    parser = argparse.ArgumentParser(description='Simple Resource Usage Analyzer')
    parser.add_argument('csv_file', help='Path to the CSV file from monitor_resources.sh')
    parser.add_argument('-o', '--output', help='Output PNG file for the visualization')
    parser.add_argument('--no-plot', action='store_true', help='Skip plotting, only show summary')
    
    args = parser.parse_args()
    
    # Validate input file
    if not Path(args.csv_file).exists():
        print(f"❌ File not found: {args.csv_file}")
        sys.exit(1)
    
    # Load and process data
    print(f"📈 Loading data from: {args.csv_file}")
    df = load_and_process_data(args.csv_file)
    
    # Print summary
    print_resource_summary(df)
    
    # Create visualization
    if not args.no_plot:
        output_file = args.output or f"resource_overview_{Path(args.csv_file).stem}.png"
        create_resource_overview(df, output_file)

if __name__ == "__main__":
    main()
