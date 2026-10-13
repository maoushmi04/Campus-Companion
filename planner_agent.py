from database import init_db, add_task, get_all_tasks_for_range, mark_task_done, is_recurring_done_today
from datetime import datetime, timedelta

def add_task_flow():
    title = input("Task title: ")
    due_date = input("Due date (YYYY-MM-DD): ")
    due_time = input("Due time (HH:MM, 24hr, or press Enter to skip): ").strip() or None
    recurring = input("Is this a daily recurring task? (y/n): ").strip().lower() == "y"
    add_task(title, due_date, due_time, recurring)
    print("Task added.\n")

def calendar_view(days_ahead=7):
    """Simple grouped-by-day list view."""
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)
    tasks = get_all_tasks_for_range(today.isoformat(), end.isoformat())

    print(f"\n--- Calendar: next {days_ahead} days ---")
    current_date = today
    while current_date <= end:
        date_str = current_date.isoformat()
        day_tasks = [t for t in tasks if t[2] == date_str or t[5] == 1]  # one-time due today, or any recurring
        if day_tasks:
            print(f"\n{current_date.strftime('%a %b %d')}:")
            for task_id, title, due_date, due_time, status, is_recurring in day_tasks:
                if is_recurring:
                    done = is_recurring_done_today(task_id, date_str)
                    mark = "✓" if done else "○"
                else:
                    mark = "✓" if status == "done" else "○"
                time_str = f" @ {due_time}" if due_time else ""
                print(f"  [{task_id}] {mark} {title}{time_str}")
        current_date += timedelta(days=1)

def diary_view(days_ahead=7):
    """More detailed, one block per day."""
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)
    tasks = get_all_tasks_for_range(today.isoformat(), end.isoformat())

    print(f"\n--- Diary view: next {days_ahead} days ---")
    current_date = today
    while current_date <= end:
        date_str = current_date.isoformat()
        day_tasks = [t for t in tasks if t[2] == date_str or t[5] == 1]
        print(f"\n=== {current_date.strftime('%A, %B %d')} ===")
        if not day_tasks:
            print("  (nothing scheduled)")
        for task_id, title, due_date, due_time, status, is_recurring in day_tasks:
            kind = "recurring daily" if is_recurring else "one-time"
            if is_recurring:
                done = is_recurring_done_today(task_id, date_str)
            else:
                done = status == "done"
            status_str = "done" if done else "not done yet"
            time_str = f" at {due_time}" if due_time else ""
            print(f"  - {title}{time_str} ({kind}, {status_str})")
        current_date += timedelta(days=1)

def complete_task_flow():
    task_id = input("Enter the task ID to mark as done (for today, if recurring): ")
    mark_task_done(int(task_id))
    print("Marked as done.\n")

def main():
    init_db()
    while True:
        print("\n1. Calendar view  2. Diary view  3. Add task  4. Mark task done  5. Quit")
        choice = input("Choose: ")
        if choice == "1":
            calendar_view()
        elif choice == "2":
            diary_view()
        elif choice == "3":
            add_task_flow()
        elif choice == "4":
            complete_task_flow()
        elif choice == "5":
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()