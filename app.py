import os
import subprocess
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
import logging

# Loggolás beállítása
logging.basicConfig(level=logging.INFO)

# --- ALAP KONFIGURÁCIÓ ---
# A kulcsokat a docker-compose.yml-ből olvassuk (környezeti változókból)
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY').encode()
cipher_suite = Fernet(ENCRYPTION_KEY)

app = Flask(__name__)
# Az adatbázis most az 'instance' mappába kerül, amit kimentünk a volume-mal
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/instance/database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
db = SQLAlchemy(app)


# --- ADATBÁZIS MODELL ---
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    db_host = db.Column(db.String(100), nullable=False)
    db_name = db.Column(db.String(100), nullable=False)
    db_user = db.Column(db.String(100), nullable=False)
    encrypted_db_pass = db.Column(db.LargeBinary)
    ftp_type = db.Column(db.String(10), nullable=False, default='sftp')
    ftp_host = db.Column(db.String(100), nullable=False)
    ftp_user = db.Column(db.String(100), nullable=False)
    encrypted_ftp_pass = db.Column(db.LargeBinary)
    remote_path = db.Column(db.String(200), nullable=False)
    local_backup_dir = db.Column(db.String(200), nullable=False, default='/backups')
    versions_to_keep = db.Column(db.Integer, default=3)
    last_backup_time = db.Column(db.String(50), default='Soha')
    last_backup_status = db.Column(db.String(500), default='Nincs információ')

    def set_password(self, password, field):
        encrypted_pass = cipher_suite.encrypt(password.encode())
        setattr(self, f"encrypted_{field}_pass", encrypted_pass)

    def get_password(self, field):
        encrypted_pass = getattr(self, f"encrypted_{field}_pass")
        if encrypted_pass:
            return cipher_suite.decrypt(encrypted_pass).decode()
        return ""

# --- WEB OLDALAK (ROUTES) ---

@app.route('/')
def index():
    projects = Project.query.order_by(Project.name).all()
    return render_template('index.html', projects=projects)

@app.route('/project/new', methods=['GET', 'POST'])
def new_project():
    if request.method == 'POST':
        project = Project(
            name=request.form['name'],
            db_host=request.form['db_host'],
            db_name=request.form['db_name'],
            db_user=request.form['db_user'],
            ftp_type=request.form['ftp_type'],
            ftp_host=request.form['ftp_host'],
            ftp_user=request.form['ftp_user'],
            remote_path=request.form['remote_path'],
            local_backup_dir=request.form.get('local_backup_dir', '/backups'),
            versions_to_keep=int(request.form.get('versions_to_keep', 3))
        )
        if request.form['db_pass']:
            project.set_password(request.form['db_pass'], 'db')
        if request.form['ftp_pass']:
            project.set_password(request.form['ftp_pass'], 'ftp')

        db.session.add(project)
        db.session.commit()
        flash(f"'{project.name}' projekt sikeresen létrehozva!", 'success')
        return redirect(url_for('index'))
    return render_template('project_form.html', project=None)

@app.route('/project/edit/<int:id>', methods=['GET', 'POST'])
def edit_project(id):
    project = Project.query.get_or_404(id)
    if request.method == 'POST':
        project.name = request.form['name']
        project.db_host = request.form['db_host']
        project.db_name = request.form['db_name']
        project.db_user = request.form['db_user']
        project.ftp_type = request.form['ftp_type']
        project.ftp_host = request.form['ftp_host']
        project.ftp_user = request.form['ftp_user']
        project.remote_path = request.form['remote_path']
        project.local_backup_dir = request.form.get('local_backup_dir', '/backups')
        project.versions_to_keep = int(request.form.get('versions_to_keep', 3))

        if request.form.get('db_pass'):
            project.set_password(request.form['db_pass'], 'db')
        if request.form.get('ftp_pass'):
            project.set_password(request.form['ftp_pass'], 'ftp')

        db.session.commit()
        flash(f"'{project.name}' projekt adatai frissítve!", 'success')
        return redirect(url_for('index'))
    return render_template('project_form.html', project=project)

@app.route('/project/delete/<int:id>', methods=['POST'])
def delete_project(id):
    project = Project.query.get_or_404(id)
    db.session.delete(project)
    db.session.commit()
    flash(f"'{project.name}' projekt törölve!", 'info')
    return redirect(url_for('index'))

@app.route('/backup/<int:id>')
def backup_project(id):
    project = Project.query.get_or_404(id)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # A mentési mappa a projekt nevét is tartalmazza a jobb átláthatóságért
    project_backup_root = os.path.join(project.local_backup_dir, project.name)
    current_backup_path = os.path.join(project_backup_root, timestamp)
    
    try:
        os.makedirs(current_backup_path, exist_ok=True)
        
        # 1. Adatbázis mentés
        db_pass = project.get_password('db')
        db_backup_file = os.path.join(current_backup_path, 'db_backup.sql')
        db_command = f"mysqldump --host={project.db_host} --user={project.db_user} --password='{db_pass}' {project.db_name} > {db_backup_file}"
        subprocess.run(db_command, check=True, shell=True, stderr=subprocess.PIPE, text=True)

        # 2. Fájlok mentése
        ftp_pass = project.get_password('ftp')
        files_backup_path = os.path.join(current_backup_path, 'files')
        lftp_command = f"lftp -u '{project.ftp_user},{ftp_pass}' {project.ftp_type}://{project.ftp_host} -e 'mirror --delete-first --verbose {project.remote_path} {files_backup_path}; quit'"
        subprocess.run(lftp_command, check=True, shell=True, stderr=subprocess.PIPE, text=True)

        # 3. Régi mentések törlése
        all_backups = sorted([d for d in os.listdir(project_backup_root) if os.path.isdir(os.path.join(project_backup_root, d))], reverse=True)
        for old_backup in all_backups[project.versions_to_keep:]:
            subprocess.run(['rm', '-rf', os.path.join(project_backup_root, old_backup)])

        project.last_backup_time = timestamp
        project.last_backup_status = 'Sikeres'
        flash(f"'{project.name}' mentése sikeres!", 'success')

    except subprocess.CalledProcessError as e:
        error_message = e.stderr or str(e)
        project.last_backup_status = f'Hiba: {error_message}'
        flash(f"'{project.name}' mentése sikertelen! Hiba: {error_message}", 'danger')
        subprocess.run(['rm', '-rf', current_backup_path])
        
    except Exception as e:
        project.last_backup_status = f'Általános hiba: {str(e)}'
        flash(f"'{project.name}' mentése sikertelen! Hiba: {str(e)}", 'danger')

    finally:
        db.session.commit()

    return redirect(url_for('index'))

if __name__ == '__main__':
    # Ezt a részt a Gunicorn használja, nem fut le közvetlenül
    app.run()