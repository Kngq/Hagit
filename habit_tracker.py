#!/usr/bin/env python3
"""
Terminal-based Habit Tracker with Constant Grid View
A simple CLI application to track habits with a constantly visible weekly grid.
"""

import contextlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple

# Celebratory one-liners for README.md when a day's habits are all completed.
PERFECT_DAY_MESSAGES = [
    "Perfect day! Every habit crushed. 🔥",
    "Full clear — nothing left unchecked! 🏆",
    "Flawless day. All habits completed. 🌟",
    "100% done. Every single habit checked off. 💪",
    "Clean sweep — great job! ✅",
    "Officially a perfect habit day! 🎉",
    "Nailed it. Not one habit skipped today. 🚀",
]

class HabitTracker:
    # ANSI color/style codes used to decorate the grid.
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"

    _ANSI_RE = re.compile(r"\033\[[0-9;]*m")

    def __init__(self, data_file: str = "habits.json"):
        self.data_file = data_file
        self.habits = self.load_habits()
        # Only emit color codes when writing to a real terminal (not a
        # pipe/file), so redirected output stays clean.
        self.use_color = sys.stdout.isatty()
        # Directory the git repo lives in - wherever the data file is.
        self.repo_dir = os.path.dirname(os.path.abspath(self.data_file))
        # Output from the most recently run command, shown above the grid
        # on the next redraw so it doesn't flash by and disappear.
        self.last_message: Optional[str] = None

    def _c(self, text: str, *codes: str) -> str:
        """Wrap text in ANSI codes, if color output is enabled."""
        if not self.use_color or not codes:
            return text
        return "".join(codes) + text + self.RESET

    @classmethod
    def _visible_len(cls, text: str) -> int:
        """Length of text as it will appear on screen, ignoring ANSI codes."""
        return len(cls._ANSI_RE.sub("", text))

    def get_monday_date(self, target_date: date) -> date:
        """Get the Monday date for the week of the target date."""
        # Monday is weekday 0 in Python's datetime (Monday=0, Sunday=6)
        days_to_monday = target_date.weekday()
        monday = target_date - timedelta(days=days_to_monday)
        return monday

    def get_week_dates(self, target_date: date = None) -> List[date]:
        """Get list of dates for Monday-Sunday of the week containing target_date."""
        if target_date is None:
            target_date = date.today()

        monday = self.get_monday_date(target_date)
        return [monday + timedelta(days=i) for i in range(7)]  # Mon-Sun

    def load_habits(self) -> Dict[str, Any]:
        """Load habits from JSON file or return empty dict if file doesn't exist."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save_habits(self):
        """Save habits to JSON file."""
        with open(self.data_file, 'w') as f:
            json.dump(self.habits, f, indent=2)

    # ---- GitHub sync -----------------------------------------------------
    # Assumes git is installed and already authenticated against GitHub
    # (an SSH key added to your account, or a configured credential
    # helper/PAT). This code never handles or stores credentials itself.

    def _run_git(self, args: List[str]) -> Tuple[bool, str]:
        """Run a git command in the repo directory. Returns (success, combined output)."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False, "git is not installed or not on PATH."
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output

    def _is_git_repo(self) -> bool:
        ok, _ = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return ok

    def _current_branch(self) -> str:
        ok, out = self._run_git(["branch", "--show-current"])
        return out if ok and out else "main"

    def _remote_default_branch(self) -> Optional[str]:
        """Branch name GitHub reports as the remote's default, without needing a fetch."""
        ok, out = self._run_git(["ls-remote", "--symref", "origin", "HEAD"])
        if not ok:
            return None
        for line in out.splitlines():
            if line.startswith("ref:"):
                # Line looks like: "ref: refs/heads/main\tHEAD"
                ref_path = line.split()[1]
                return ref_path.rsplit("/", 1)[-1]
        return None

    def connect_repo(self, repo_url: str) -> bool:
        """Link this tracker to a GitHub repo, adopting any data already there."""
        if not self._is_git_repo():
            ok, out = self._run_git(["init"])
            if not ok:
                print(f"Failed to initialize a git repo here: {out}")
                return False

        has_origin, _ = self._run_git(["remote", "get-url", "origin"])
        if has_origin:
            ok, out = self._run_git(["remote", "set-url", "origin", repo_url])
        else:
            ok, out = self._run_git(["remote", "add", "origin", repo_url])
        if not ok:
            print(f"Failed to set the 'origin' remote: {out}")
            return False

        remote_branch = self._remote_default_branch()
        has_local_commits, _ = self._run_git(["rev-parse", "HEAD"])

        if remote_branch and not has_local_commits:
            # Remote already has history and we don't - adopt it instead of
            # clobbering whatever's there (e.g. tracker used on another machine).
            fetch_ok, fetch_out = self._run_git(["fetch", "origin", remote_branch])
            if not fetch_ok:
                print(f"Failed to fetch from {repo_url}: {fetch_out}")
                return False
            ok, out = self._run_git(["checkout", "-B", remote_branch, f"origin/{remote_branch}"])
            if not ok:
                print(f"Failed to check out '{remote_branch}': {out}")
                return False
            self.habits = self.load_habits()
            print(f"Connected to {repo_url} - pulled down its existing habit data onto branch '{remote_branch}'.")
            return True

        if remote_branch and has_local_commits:
            print(f"Connected to {repo_url}.")
            print(f"Both your local history and the remote's '{remote_branch}' branch have commits - run 'pull' to merge them before your first 'push'.")
            return True

        # Remote is brand new/empty: make sure we have an initial commit, then push it up.
        branch = self._current_branch()
        if not has_local_commits:
            self.save_habits()
            self._run_git(["add", self.data_file])
            if os.path.exists(self._readme_path()):
                self._run_git(["add", self.README_FILENAME])
            self._run_git(["commit", "-m", "Initial habit tracker data"])

        push_ok, push_out = self._run_git(["push", "-u", "origin", branch])
        if not push_ok:
            print(f"Connected to {repo_url}, but the initial push failed:\n{push_out}")
            print("Make sure GitHub authentication is set up (SSH key or credential helper), then run 'push' again.")
            return False

        print(f"Connected to {repo_url} and pushed initial habit data to '{branch}'.")
        return True

    def push_habits(self, message: str = None) -> bool:
        """Commit and push the current habit data to the connected GitHub repo."""
        if not self._is_git_repo():
            print("Not connected to a repo yet. Run 'connect <github-repo-url>' first.")
            return False

        has_origin, origin_url = self._run_git(["remote", "get-url", "origin"])
        if not has_origin:
            print("No remote repo configured. Run 'connect <github-repo-url>' first.")
            return False

        self.save_habits()  # make sure disk matches memory before staging
        add_ok, add_out = self._run_git(["add", self.data_file])
        if not add_ok:
            print(f"Failed to stage {self.data_file}: {add_out}")
            return False

        if os.path.exists(self._readme_path()):
            self._run_git(["add", self.README_FILENAME])

        nothing_staged, _ = self._run_git(["diff", "--cached", "--quiet"])
        if nothing_staged:
            print("Nothing to push - habit data already matches the last sync.")
            return True

        commit_message = message or f"Update habits - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        commit_ok, commit_out = self._run_git(["commit", "-m", commit_message])
        if not commit_ok:
            print(f"Failed to commit changes: {commit_out}")
            return False

        branch = self._current_branch()
        push_ok, push_out = self._run_git(["push", "origin", branch])
        if push_ok:
            print(f"Pushed habit updates to {origin_url} ({branch}).")
            return True

        if "rejected" in push_out.lower() or "non-fast-forward" in push_out.lower():
            print("Remote has newer commits - pulling and retrying...")
            pull_ok, pull_out = self._run_git(["pull", "--rebase", "origin", branch])
            if pull_ok:
                push_ok, push_out = self._run_git(["push", "origin", branch])
                if push_ok:
                    self.habits = self.load_habits()
                    print(f"Pushed habit updates to {origin_url} ({branch}).")
                    return True
            else:
                print(f"Automatic pull failed - resolve manually:\n{pull_out}")
                return False

        print(f"Failed to push: {push_out}")
        return False

    def pull_habits(self) -> bool:
        """Pull the latest habit data from the connected GitHub repo."""
        if not self._is_git_repo():
            print("Not connected to a repo yet. Run 'connect <github-repo-url>' first.")
            return False

        has_origin, origin_url = self._run_git(["remote", "get-url", "origin"])
        if not has_origin:
            print("No remote repo configured. Run 'connect <github-repo-url>' first.")
            return False

        branch = self._current_branch()
        pull_ok, pull_out = self._run_git(["pull", "--rebase", "origin", branch])
        if not pull_ok:
            print(f"Pull failed: {pull_out}")
            return False

        self.habits = self.load_habits()
        print(f"Pulled latest habit data from {origin_url} ({branch}).")
        return True

    # ---- README "perfect day" log -----------------------------------------
    # When every tracked habit is completed for a given date, we log a fun
    # one-liner in README.md. It's written locally right away; like
    # habits.json, it only reaches GitHub on the next 'push'/'sync'.

    README_FILENAME = "README.md"
    _README_HEADER = "# Habit Tracker\n\n## 🎉 Completion Log\n\n"
    _ENTRY_PREFIX_RE = r"^- \*\*{date}\*\* — .*$\n?"

    def _readme_path(self) -> str:
        return os.path.join(self.repo_dir, self.README_FILENAME)

    def _all_habits_completed_on(self, date_str: str) -> bool:
        """True if every currently-tracked habit is marked done for date_str."""
        if not self.habits:
            return False
        return all(
            habit.get("completions", {}).get(date_str, False)
            for habit in self.habits.values()
        )

    def _log_perfect_day(self, date_str: str):
        """Append a celebratory entry for date_str to README.md (no-op if already logged)."""
        path = self._readme_path()
        content = ""
        if os.path.exists(path):
            with open(path, "r") as f:
                content = f.read()
        if not content.strip():
            content = self._README_HEADER

        already_logged = re.search(
            self._ENTRY_PREFIX_RE.format(date=re.escape(date_str)), content, re.MULTILINE
        )
        if already_logged:
            return

        if not content.endswith("\n"):
            content += "\n"
        content += f"- **{date_str}** — {random.choice(PERFECT_DAY_MESSAGES)}\n"

        with open(path, "w") as f:
            f.write(content)

        print(self._c(
            f"🎉 All habits completed for {date_str}! Logged it in README.md (run 'push' to publish).",
            self.BOLD, self.GREEN
        ))

    def _unlog_day(self, date_str: str):
        """Remove date_str's entry from README.md, if one exists."""
        path = self._readme_path()
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            content = f.read()
        new_content, removed = re.subn(
            self._ENTRY_PREFIX_RE.format(date=re.escape(date_str)), "", content, flags=re.MULTILINE
        )
        if removed:
            with open(path, "w") as f:
                f.write(new_content)

    def add_habit(self, name: str):
        """Add a new habit."""
        if name in self.habits:
            print(f"Habit '{name}' already exists!")
            return False

        self.habits[name] = {
            "created": date.today().isoformat(),
            "completions": {}  # date_string (YYYY-MM-DD) -> True/False
        }
        self.save_habits()
        print(f"Habit '{name}' added successfully!")
        return True

    def complete_habit(self, name: str, target_date: str = None):
        """Mark a habit as completed for a specific date."""
        if name not in self.habits:
            print(f"Habit '{name}' not found!")
            return False

        if target_date is None:
            target_date = date.today().isoformat()

        # Validate date format
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD")
            return False

        self.habits[name]["completions"][target_date] = True
        self.save_habits()
        print(f"Habit '{name}' marked as completed for {target_date}!")

        if self._all_habits_completed_on(target_date):
            self._log_perfect_day(target_date)

        return True

    def uncheck_habit(self, name: str, target_date: str = None):
        """Unmark a habit as completed for a specific date."""
        if name not in self.habits:
            print(f"Habit '{name}' not found!")
            return False

        if target_date is None:
            target_date = date.today().isoformat()

        # Validate date format
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD")
            return False

        habit = self.habits[name]
        completions = habit.get("completions", {})

        # If the date exists in completions, set it to False
        # If it doesn't exist, we can still add it as False (explicitly not completed)
        completions[target_date] = False
        self.save_habits()
        print(f"Habit '{name}' unmarked for {target_date}!")

        # This habit is no longer done on target_date, so the day can't be
        # "perfect" anymore - drop any celebratory entry that said otherwise.
        self._unlog_day(target_date)

        return True

    def remove_habit(self, name: str):
        """Remove a habit entirely."""
        if name not in self.habits:
            print(f"Habit '{name}' not found!")
            return False

        del self.habits[name]
        self.save_habits()
        print(f"Habit '{name}' removed successfully!")
        return True

    def get_weekly_progress(self, name: str, week_dates: List[date]) -> float:
        """Get completion percentage for a habit for a specific week."""
        if name not in self.habits:
            return 0.0

        habit = self.habits[name]
        completions = habit.get("completions", {})

        # Count how many days in this week were completed
        completed_days = 0
        for dt in week_dates:
            date_str = dt.isoformat()
            if completions.get(date_str, False):
                completed_days += 1

        # Percentage based on 7 days in the week
        return (completed_days / 7) * 100

    def _print_centered(self, lines: List[str]):
        """Print a block of lines centered horizontally in the terminal.

        All lines get the same left padding (based on the widest line and
        the current terminal width), so the block is centered as a whole
        without disturbing the column alignment within it.
        """
        term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
        block_width = max((self._visible_len(line) for line in lines), default=0)
        pad = " " * max(0, (term_width - block_width) // 2)
        for line in lines:
            print(f"{pad}{line}")

    def display_habits(self):
        """Display all habits in a weekly grid view (Monday-Sunday), centered in the terminal.

        Clears the terminal first so only the newest version of the table
        is ever visible (no stacked history of past redraws).
        """
        os.system('cls' if os.name == 'nt' else 'clear')

        if self.last_message:
            self._print_centered(self.last_message.splitlines())
            print()

        if not self.habits:
            self._print_centered([self._c("No habits tracked yet. Use 'add' to add a new habit.", self.DIM)])
            return

        # Get current week dates (Monday-Sunday)
        week_dates = self.get_week_dates()
        today = date.today()

        # Create header with day names and star for current day
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        header_parts = []
        for i, (day_name, dt) in enumerate(zip(day_names, week_dates)):
            if dt == today:
                header_parts.append(self._c(f"{day_name}★", self.BOLD, self.YELLOW))  # Highlight current day
            else:
                header_parts.append(f"{day_name} ")

        header = "  ".join(header_parts)
        header_visible_len = self._visible_len(header)

        habit_col = self._c(f"{'Habit':<15}", self.BOLD)
        pct_col = self._c("%", self.BOLD)

        lines = [
            self._c("="*60, self.CYAN),
            self._c("WEEKLY HABIT TRACKER", self.BOLD, self.CYAN),
            self._c("="*60, self.CYAN),
            self._c(f"Week of {week_dates[0]} to {week_dates[6]}", self.DIM),
            "",
            f"{habit_col} {header}  {pct_col}",
            self._c("-" * (15 + header_visible_len + 4), self.DIM),
        ]

        # Build each habit row
        for habit_name, habit_data in self.habits.items():
            completions = habit_data.get("completions", {})

            # Build row of checkboxes for each day in the week
            row_parts = []
            for dt in week_dates:
                date_str = dt.isoformat()
                if completions.get(date_str, False):
                    row_parts.append(self._c("[x] ", self.GREEN))  # Completed
                else:
                    row_parts.append(self._c("[ ] ", self.DIM))  # Not completed

            row = "  ".join(row_parts)
            # Get percentage for this week
            progress = self.get_weekly_progress(habit_name, week_dates)
            if progress >= 70:
                progress_color = self.GREEN
            elif progress >= 40:
                progress_color = self.YELLOW
            else:
                progress_color = self.RED
            progress_str = self._c(f"{progress:3.0f}%", progress_color)

            habit_label = self._c(f"{habit_name:<15}", self.BOLD)
            lines.append(f"{habit_label} {row}  {progress_str}")

        lines.append("")
        legend = (
            "Legend: " + self._c("[x]", self.GREEN) + " = completed, "
            + self._c("[ ]", self.DIM) + " = not completed, "
            + self._c("★", self.BOLD, self.YELLOW) + " = today"
        )
        lines.append(legend)

        print()
        self._print_centered(lines)

    def list_commands(self):
        """List available commands."""
        print("\nAvailable commands:")
        print("  add <habit_name>     - Add a new habit")
        print("  remove <habit_name>  - Remove a habit")
        print("  complete <habit_name> [date] - Mark habit as completed (date format: YYYY-MM-DD, defaults to today)")
        print("  uncheck <habit_name> [date] - Unmark habit as completed (date format: YYYY-MM-DD, defaults to today)")
        print("  connect <github-repo-url> - Link this tracker to a (private) GitHub repo")
        print("  push / sync          - Commit and push current habit data to the connected repo")
        print("  pull                 - Pull the latest habit data from the connected repo")
        print("  help                 - Show this help")
        print("  quit/exit            - Exit the application")
        print()
        print("Note: completing every habit for a day adds a fun entry to README.md.")
        print("It's saved locally right away; run 'push'/'sync' to publish it with your habit data.")

def main():
    tracker = HabitTracker()
    # Shown above the grid on the very first draw, same mechanism as every
    # later command's output.
    tracker.last_message = "Welcome to the Terminal Habit Tracker!\nType 'help' for available commands."

    while True:
        try:
            # Constantly display the habit grid
            tracker.display_habits()

            # Show prompt and get input
            command_input = input("\n> ").strip()
            if not command_input:
                continue

            parts = command_input.split()
            command = parts[0].lower()

            if command in ["quit", "exit"]:
                print("Goodbye!")
                break

            # Run the command with its output captured, instead of printed
            # straight to the terminal - display_habits() will show it above
            # the grid on the next redraw so it doesn't flash by and vanish
            # the instant the screen clears.
            output_buffer = io.StringIO()
            with contextlib.redirect_stdout(output_buffer):
                _run_command(tracker, command, parts)
            captured = output_buffer.getvalue().rstrip("\n")
            if captured:
                tracker.last_message = captured

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break

def _run_command(tracker: HabitTracker, command: str, parts: List[str]):
    """Dispatch one parsed command. Runs with stdout captured by the caller."""
    if command == "help":
        tracker.list_commands()
    elif command == "add":
        if len(parts) < 2:
            print("Usage: add <habit_name>")
        else:
            habit_name = " ".join(parts[1:])
            tracker.add_habit(habit_name)
    elif command == "remove":
        if len(parts) < 2:
            print("Usage: remove <habit_name>")
        else:
            habit_name = " ".join(parts[1:])
            tracker.remove_habit(habit_name)
    elif command == "complete":
        if len(parts) < 2:
            print("Usage: complete <habit_name> [date]")
        else:
            # Check if last argument is a valid date
            habit_name = None
            target_date = None

            if len(parts) == 2:
                # Only habit name provided
                habit_name = parts[1]
            else:
                # Check if last part is a valid date
                potential_date = parts[-1]
                try:
                    datetime.strptime(potential_date, "%Y-%m-%d")
                    # It's a valid date
                    habit_name = " ".join(parts[1:-1])
                    target_date = potential_date
                except ValueError:
                    # Not a valid date, treat as part of habit name
                    habit_name = " ".join(parts[1:])

            if habit_name is not None:
                tracker.complete_habit(habit_name, target_date)
    elif command == "uncheck":
        if len(parts) < 2:
            print("Usage: uncheck <habit_name> [date]")
        else:
            # Check if last argument is a valid date
            habit_name = None
            target_date = None

            if len(parts) == 2:
                # Only habit name provided
                habit_name = parts[1]
            else:
                # Check if last part is a valid date
                potential_date = parts[-1]
                try:
                    datetime.strptime(potential_date, "%Y-%m-%d")
                    # It's a valid date
                    habit_name = " ".join(parts[1:-1])
                    target_date = potential_date
                except ValueError:
                    # Not a valid date, treat as part of habit name
                    habit_name = " ".join(parts[1:])

            if habit_name is not None:
                tracker.uncheck_habit(habit_name, target_date)
    elif command == "connect":
        if len(parts) < 2:
            print("Usage: connect <github-repo-url>")
        else:
            tracker.connect_repo(parts[1])
    elif command in ("push", "sync"):
        tracker.push_habits()
    elif command == "pull":
        tracker.pull_habits()
    else:
        print(f"Unknown command: {command}")
        print("Type 'help' for available commands.")

if __name__ == "__main__":
    main()