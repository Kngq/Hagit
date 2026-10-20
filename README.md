# Hagit

A terminal-based habit tracker with a constantly-visible weekly grid — and it can push your habit data straight to a GitHub repo, so your streaks live in your commit history (and, if you want, your GitHub contribution graph).

```
============================================================
                 WEEKLY HABIT TRACKER
============================================================
          Week of 2026-10-19 to 2026-10-25

Habit           Mon   Tue   Wed★  Thu   Fri   Sat   Sun     %
----------------------------------------------------------------
Read            [x]   [x]   [ ]   [ ]   [ ]   [ ]   [ ]    29%
Workout         [x]   [ ]   [ ]   [ ]   [ ]   [ ]   [ ]    14%

Legend: [x] = completed, [ ] = not completed, ★ = today
```

## Features

- Always-on weekly grid view (Monday–Sunday), redrawn after every command
- Simple commands to add, remove, complete, and uncheck habits
- Per-habit weekly completion percentage, color-coded
- Optional one-command sync to a GitHub repo (`connect`, `push`/`sync`, `pull`)
- Logs a celebratory note in this README whenever every habit is completed for a day

## Requirements

- Python 3.8+
- `git` installed and on your `PATH`
- No third-party packages — everything used is in the Python standard library

## Download

Clone the repo:

```bash
git clone https://github.com/Kngq/Hagit.git
cd Hagit
```

Or just download `habit_tracker.py` directly if you don't need the sync-to-GitHub feature.

## Usage

Run it:

```bash
python3 habit_tracker.py
```

You'll land on the weekly grid with a `>` prompt underneath. Available commands:

| Command | Description |
|---|---|
| `add <habit_name>` | Add a new habit |
| `remove <habit_name>` | Remove a habit |
| `complete <habit_name> [date]` | Mark a habit completed (date is `YYYY-MM-DD`, defaults to today) |
| `uncheck <habit_name> [date]` | Unmark a habit for a date |
| `connect <github-repo-url>` | Link this tracker to a GitHub repo |
| `push` / `sync` | Commit and push your current habit data |
| `pull` | Pull the latest habit data from the connected repo |
| `help` | Show the command list |
| `quit` / `exit` | Exit |

### Syncing your habits to GitHub

1. Create a repo on GitHub (a private one is fine).
2. Make sure `git` is authenticated for pushing — either an SSH key added to your GitHub account, or a credential helper/PAT set up for HTTPS.
3. Inside the tracker, run:

   ```
   > connect https://github.com/<you>/<your-repo>.git
   ```

4. From then on, running `push` (or `sync`) commits `habits.json` and this README, and pushes them up.

**Want the commits to show up on your GitHub profile's contribution graph?** Git attributes commits by the email in your local git config, not by who's typing — so that email needs to match a verified email on your GitHub account. Set it (globally, or just for this repo by dropping `--global`):

```bash
git config --global user.email "your-github-email@example.com"
```

If this doesn't match an email verified on your GitHub account, the commits will still push fine, they just won't count toward your contribution graph.

## How your data is stored

Habits live in `habits.json`, tracked alongside the code so your history travels with the repo. Every habit has a `created` date and a map of `date -> completed`. Nothing here ever handles your git credentials directly — it shells out to your already-authenticated `git`.
