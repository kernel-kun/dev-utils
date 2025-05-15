#!/usr/bin/env python3
"""
Script to perform various set operations between two files.
Each file is expected to have entries on separate lines.
Supports Union, Intersection, Difference (A-B, B-A), and Symmetric Difference.
Outputs both Excel and text reports.
"""

import argparse
import os
from typing import Dict, Optional, Set, Tuple

import pandas as pd


def get_input_data() -> Tuple[Set[str], Set[str]]:
    """Get input data either from command line arguments or interactive input."""
    parser = argparse.ArgumentParser(
        description="Perform set operations between two files or direct input"
    )
    parser.add_argument("--file1", help="First file path")
    parser.add_argument("--file2", help="Second file path")
    parser.add_argument("--input1", help="First set of items (comma-separated)")
    parser.add_argument("--input2", help="Second set of items (comma-separated)")
    parser.add_argument(
        "--operations",
        help="Comma-separated list of operations to perform (union,intersection,difference_ab,difference_ba,symmetric_difference)",
    )
    parser.add_argument(
        "--output-prefix",
        default="set_operations",
        help="Prefix for output files (default: set_operations)",
    )
    args = parser.parse_args()

    set1: Set[str] = set()
    set2: Set[str] = set()

    if args.file1 and args.file2:
        set1 = read_file_lines(args.file1)
        set2 = read_file_lines(args.file2)
    elif args.input1 and args.input2:
        set1 = {item.strip() for item in args.input1.split(",") if item.strip()}
        set2 = {item.strip() for item in args.input2.split(",") if item.strip()}
    else:
        # Interactive input
        print("\nNo input provided via arguments. Please provide input interactively:")
        choice = input("Enter 1 for file input, 2 for direct input: ").strip()

        if choice == "1":
            file1 = input("\nEnter path for first file: ").strip()
            file2 = input("Enter path for second file: ").strip()
            set1 = read_file_lines(file1)
            set2 = read_file_lines(file2)
        else:
            print("\nEnter items for first set (comma-separated):")
            items1 = input().strip()
            print("Enter items for second set (comma-separated):")
            items2 = input().strip()
            set1 = {item.strip() for item in items1.split(",") if item.strip()}
            set2 = {item.strip() for item in items2.split(",") if item.strip()}
        if not set1 or not set2:
            raise ValueError("Both sets must not be empty")

    # Handle operations input
    operations = args.operations
    if (
        not operations and not args.file1 and not args.input1
    ):  # Only ask if in interactive mode
        print("\nAvailable set operations:")
        print("1. Union (A ∪ B) - Items present in either set")
        print("2. Intersection (A ∩ B) - Items present in both sets")
        print("3. Difference A-B - Items in first set but not in second set")
        print("4. Difference B-A - Items in second set but not in first set")
        print("5. Symmetric Difference (A △ B) - Items in either set but not in both")
        print("\nEnter the numbers of operations you want to perform (comma-separated)")
        print("Leave empty to perform all operations")

        op_choice = input().strip()
        if op_choice:
            # Map user's number choices to operation names
            op_map = {
                "1": "union",
                "2": "intersection",
                "3": "difference_ab",
                "4": "difference_ba",
                "5": "symmetric_difference",
            }
            operations = ",".join(
                op_map[num.strip()]
                for num in op_choice.split(",")
                if num.strip() in op_map
            )

    return set1, set2, operations, args.output_prefix


def read_file_lines(file_path: str) -> Set[str]:
    """Read lines from a file and return as a set."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} does not exist.")

    with open(file_path, "r") as file:
        return {line.strip() for line in file if line.strip()}


def perform_set_operations(
    set1: Set[str], set2: Set[str], operations: Optional[str] = None
) -> Dict[str, Set[str]]:
    """Perform requested set operations between two sets."""
    available_operations = {
        "union": lambda a, b: a | b,
        "intersection": lambda a, b: a & b,
        "difference_ab": lambda a, b: a - b,
        "difference_ba": lambda a, b: b - a,
        "symmetric_difference": lambda a, b: a ^ b,
    }

    if operations:
        requested_ops = [op.strip() for op in operations.split(",")]
        operations_to_perform = {
            op: func for op, func in available_operations.items() if op in requested_ops
        }
    else:
        operations_to_perform = available_operations

    results = {}
    for op_name, op_func in operations_to_perform.items():
        results[op_name] = op_func(set1, set2)

    return results


def write_results_to_files(results: Dict[str, Set[str]], output_prefix: str) -> None:
    """Write results to both Excel and text files."""
    # Prepare Excel file
    xlsx_file = f"{output_prefix}.xlsx"
    writer = pd.ExcelWriter(xlsx_file, engine="openpyxl")

    # Prepare text file
    txt_file = f"{output_prefix}.txt"

    operation_descriptions = {
        "union": "Items present in either set (A ∪ B)",
        "intersection": "Items present in both sets (A ∩ B)",
        "difference_ab": "Items in first set but not in second set (A - B)",
        "difference_ba": "Items in second set but not in first set (B - A)",
        "symmetric_difference": "Items in either set but not in both (A △ B)",
    }

    # Write to Excel file
    for op_name, result_set in results.items():
        if result_set:  # Only create sheet if there are results
            df = pd.DataFrame(sorted(result_set), columns=[op_name])
            df.to_excel(writer, sheet_name=op_name, index=False)

    writer.close()

    # Write to text file
    with open(txt_file, "w") as f:
        for op_name, result_set in results.items():
            f.write(f"\n{operation_descriptions[op_name]}\n")
            f.write("=" * 50 + "\n")
            if result_set:
                for item in sorted(result_set):
                    f.write(f"{item}\n")
            else:
                f.write("No items found\n")
            f.write("\n")


def main():
    """Main execution function."""
    try:
        # Get input data
        set1, set2, operations, output_prefix = get_input_data()

        print("\nPerforming set operations...")
        results = perform_set_operations(set1, set2, operations)

        # Generate output files
        output_prefix = output_prefix or "set_operations"
        write_results_to_files(results, output_prefix)

        print("\nResults have been written to:")
        print(f"- Excel file: {output_prefix}.xlsx")
        print(f"- Text file: {output_prefix}.txt")

        # Print summary
        print("\nSummary:")
        for op_name, result_set in results.items():
            print(f"{op_name}: {len(result_set)} items")

    except Exception as e:
        print(f"\nError: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
