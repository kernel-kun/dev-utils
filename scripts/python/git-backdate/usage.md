# Git Backdate Script Usage Guide

A comprehensive guide for using the [`git-backdate`](.scripts/git-backdate) script to modify commit timestamps.

## Overview

This Python script allows you to backdate one or more Git commits to specific dates or date ranges. It uses interactive rebase under the hood and modifies both author and committer dates.

## Basic Syntax

```bash
.scripts/git-backdate <COMMITS> <DATES> [OPTIONS]
```

## Commit Selection (First Argument)

The `COMMITS` argument specifies which commits to backdate. The script interprets this in several ways:

### 1. Single Commit (Current/HEAD)

Backdate only the most recent commit:

```bash
# Using HEAD
.scripts/git-backdate HEAD "yesterday"

# Using @ (shorthand for HEAD)
.scripts/git-backdate @ "yesterday"
```

**How it works:** `HEAD` or `@` is converted to `HEAD^..HEAD` internally, selecting only the latest commit.

### 2. All Commits from Root

Backdate the entire repository history:

```bash
.scripts/git-backdate ROOT "2024-01-01..2024-06-30"
```

**How it works:** `ROOT` selects all commits from the first commit to HEAD.

### 3. Uncommitted Commits on Current Branch (Compared to Another Branch)

Backdate all commits that exist on your current branch but not on another branch:

```bash
# Commits not in main
.scripts/git-backdate main "last week..yesterday"

# Commits not in develop
.scripts/git-backdate develop "2024-01-15..2024-01-20"

# Commits not in origin/main
.scripts/git-backdate origin/main "3 days ago..yesterday"
```

**How it works:** `<branch>` is converted to `<branch>..HEAD`, selecting all commits reachable from HEAD but not from the specified branch.

### 4. Commits Since a Specific SHA

Backdate all commits after a specific commit:

```bash
# All commits after abc1234
.scripts/git-backdate abc1234 "last month..yesterday"

# Using full SHA
.scripts/git-backdate a1b2c3d4e5f6g7h8i9j0 "2024-02-01..2024-02-28"
```

**How it works:** `<SHA>` is converted to `<SHA>..HEAD`.

### 5. Explicit Commit Range

Backdate a specific range of commits:

```bash
# From commit A to commit B (exclusive of A)
.scripts/git-backdate abc1234..def5678 "last week"

# From a branch point to a specific commit
.scripts/git-backdate main..feature-branch "2024-03-01..2024-03-15"

# Open-ended range (to HEAD)
.scripts/git-backdate abc1234.. "yesterday"
```

### 6. Using Git References

```bash
# Commits in the last 5 commits
.scripts/git-backdate HEAD~5 "last week..today"

# Commits since a tag
.scripts/git-backdate v1.0.0 "2024-01-01..2024-01-31"

# Commits between two tags
.scripts/git-backdate v1.0.0..v2.0.0 "2024-01-01..2024-06-30"
```

## Date Selection (Second Argument)

The `DATES` argument specifies when to backdate the commits to.

### 1. Single Date

All commits will be distributed throughout a single day:

```bash
.scripts/git-backdate HEAD "2024-06-15"
.scripts/git-backdate HEAD "yesterday"
.scripts/git-backdate HEAD "last friday"
```

### 2. Date Range

Commits are distributed across the date range:

```bash
# ISO format
.scripts/git-backdate main "2024-01-01..2024-01-31"

# Human-readable
.scripts/git-backdate main "last month..yesterday"
.scripts/git-backdate main "2 weeks ago..3 days ago"

# Mixed formats
.scripts/git-backdate main "2024-01-01..yesterday"
```

### Supported Date Formats

The script uses your system's `date` command (or `gdate` on macOS) to parse dates:

| Format | Example |
|--------|---------|
| ISO 8601 | `2024-06-15` |
| Relative | `yesterday`, `today`, `tomorrow` |
| Relative with units | `3 days ago`, `2 weeks ago`, `1 month ago` |
| Named days | `last monday`, `next friday` |
| Named periods | `last week`, `last month` |

## Options

### `--business-hours`

Restrict timestamps to business hours (Monday–Friday, 9:00–17:00):

```bash
.scripts/git-backdate main "last week..yesterday" --business-hours
```

### `--no-business-hours`

Restrict timestamps to outside business hours (18:00–23:00, every day):

```bash
.scripts/git-backdate main "last week..yesterday" --no-business-hours
```

**Note:** `--business-hours` and `--no-business-hours` are mutually exclusive.

### `--except-days`

Exclude specific dates from the backdating range:

```bash
# Exclude a single day
.scripts/git-backdate main "2024-01-01..2024-01-31" --except-days "2024-01-15"

# Exclude multiple days (comma-separated)
.scripts/git-backdate main "2024-01-01..2024-01-31" --except-days "2024-01-15,2024-01-20"

# Exclude a date range
.scripts/git-backdate main "2024-01-01..2024-01-31" --except-days "2024-01-10..2024-01-15"

# Combine single dates and ranges
.scripts/git-backdate main "2024-01-01..2024-01-31" --except-days "2024-01-01,2024-01-15..2024-01-17,2024-01-25"
```

### `--log-level`

Control verbosity of output:

```bash
.scripts/git-backdate main "last week" --log-level DEBUG
.scripts/git-backdate main "last week" --log-level INFO
.scripts/git-backdate main "last week" --log-level WARNING  # default
.scripts/git-backdate main "last week" --log-level ERROR
```

## Common Use Cases

### 1. Backdate Today's Commits to Look Like Yesterday's Work

```bash
.scripts/git-backdate main "yesterday" --business-hours
```

### 2. Spread a Week's Worth of Commits Across the Month

```bash
.scripts/git-backdate main "2024-01-01..2024-01-31" --business-hours
```

### 3. Make Weekend Commits Look Like Weekday Work

```bash
.scripts/git-backdate HEAD~10 "last monday..last friday" --business-hours
```

### 4. Backdate Feature Branch Before Merging

```bash
.scripts/git-backdate develop "2024-02-01..2024-02-14" --business-hours --except-days "2024-02-05,2024-02-06"
```

### 5. Fix a Single Commit's Date

```bash
.scripts/git-backdate HEAD "2024-03-15"
```

### 6. Backdate All Unpushed Commits

```bash
.scripts/git-backdate origin/main "last week..yesterday" --business-hours
```

### 7. Simulate After-Hours Coding

```bash
.scripts/git-backdate main "last week..yesterday" --no-business-hours
```

### 8. Backdate Entire Repository (New Project Setup)

```bash
.scripts/git-backdate ROOT "2024-01-01..2024-06-30" --business-hours
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GIT_BACKDATE_DATE_CMD` | Override the date parsing command | `date` (Linux) or `gdate` (macOS) |

## How It Works

1. **Commit Resolution:** The script resolves the commit range using `git rev-list`
2. **Date Parsing:** Dates are parsed using the system's `date` command
3. **Interactive Rebase:** Starts an interactive rebase from the first commit's parent
4. **Timestamp Distribution:** Commits are distributed across the date range with random times
5. **Date Modification:** Both author date and committer date are updated for each commit

## Important Notes

⚠️ **Warning:** This script rewrites Git history. Only use on commits that haven't been pushed, or be prepared to force-push.

- The script will abort if a rebase is already in progress
- If an error occurs during rebase, the script automatically aborts to leave your repo clean
- Commits are distributed proportionally across the date range
- With `--business-hours`, weekends are automatically excluded
- The script ensures commit timestamps remain in chronological order

## Troubleshooting

### "Current commit is not an ancestor of the commit range"

You're trying to backdate commits that aren't in your current branch's history. Make sure you're on the correct branch.

### "No commits found"

The commit range resolved to zero commits. Check your commit reference syntax.

### macOS Date Parsing Issues

Install GNU date via Homebrew:

```bash
brew install coreutils
```

The script will automatically use `gdate` on macOS.
