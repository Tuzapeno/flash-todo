# ⚡ Flash Todo

TODO: Add image

A minimal terminal task manager built to keep me on track when solving complex problems.

## Why this exists

I kept losing focus. I'd be deep into a problem, branch off to fix something else, then forget what I was originally doing — or worse, forget the three things I uncovered along the way. Traditional todo apps didn't help because they're built for long-term planning, recurring schedules, and life organization. I didn't need any of that. I needed something I could pull up in a terminal, dump my current mental stack into, and get back to work.

Flash Todo is that. It's a scratchpad with structure, designed for short-term tasks, not weekly planning or habit tracking.

## How it works

Tasks are organized as a **tree**. You start with root tasks, and when a task turns out to be more complex than expected, you **branch** it into subtasks. You can keep branching as deep as you need. When all branches of a task are done, the parent completes automatically.

### Projects

Tasks can be grouped into **projects** for visual organization. Each project gets a unique color in the UI. You can assign a project with `[P]`, or inline when creating a task using an `@` tag:

```
buy milk @groceries
fix auth bug @backend
```

## Controls

| Key | Action |
|---|---|
| `A` | Add a new task (root or branch, depending on current level) |
| `B` | Branch/divide the selected task into subtasks |
| `P` | Assign a project to the selected task |
| `R` | Rename the selected task |
| `Space` | Toggle completion (leaf tasks only) |
| `Enter` / `→` / `L` | Zoom into a task's branches |
| `Esc` / `←` / `H` | Zoom out to the parent level |
| `↑` / `K` | Move selection up |
| `↓` / `J` | Move selection down |
| `D` / `Delete` | Delete a task and all its branches |
| `Q` | Quit |

## TODO: Add usage

Tasks are saved to `~/.branch_tasks/tasks.json`.
