from datetime import datetime, timedelta
from app import app, Project, db, _run_backup_logic

def is_backup_due(project):
    if project.last_backup_time == 'Soha':
        print(f"-> Backup is due for '{project.name}' (never backed up before).")
        return True
    
    try:
        last_backup_date = datetime.strptime(project.last_backup_time, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        print(f"-> Could not parse last backup time for '{project.name}', assuming it's due.")
        return True
        
    schedule = project.backup_schedule
    now = datetime.now()
    
    if schedule == 'daily' and now > last_backup_date + timedelta(hours=23):
        print(f"-> Backup is due for '{project.name}' (daily schedule).")
        return True
    if schedule == 'weekly' and now > last_backup_date + timedelta(days=6):
        print(f"-> Backup is due for '{project.name}' (weekly schedule).")
        return True
    if schedule == 'monthly' and now > last_backup_date + timedelta(days=29):
        print(f"-> Backup is due for '{project.name}' (monthly schedule).")
        return True
        
    return False

def run_scheduled_backups():
    with app.app_context():
        print(f"[{datetime.now()}] --- Starting scheduled backup check ---")
        
        projects_to_check = Project.query.filter(Project.backup_schedule != 'manual').all()
        
        if not projects_to_check:
            print("No projects with automatic schedules found.")
        
        for project in projects_to_check:
            if is_backup_due(project):
                try:
                    print(f"-> Running backup for '{project.name}'...")
                    _run_backup_logic(project)
                    print(f"-> SUCCESS: Backup for '{project.name}' completed.")
                except Exception as e:
                    project.last_backup_status = f'AUTOMATIC BACKUP FAILED: {str(e)}'
                    db.session.commit()
                    print(f"-> ERROR: Backup for '{project.name}' failed. Error: {e}")
            else:
                print(f"-> Backup is not yet due for project: '{project.name}'")
        
        print(f"[{datetime.now()}] --- Backup check finished ---")

if __name__ == '__main__':
    run_scheduled_backups()