import os
import subprocess
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
import logging

# Loggolás beállítása
logging.basicConfig(level=logging.INFO)

# --- ALAP KONFIGURÁCIÓ ---
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY').encode()
cipher_suite = Fernet(ENCRYPTION_KEY)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/instance/database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
db = SQLAlchemy(app)


# --- ADATBÁZIS MODELL (FRISSÍTVE) ---
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    
    # --- ÚJ MEZŐ A MENTÉSI MÓD VÁLASZTÁSÁHOZ ---
    backup_method = db.Column(db.String(50), nullable=False, default='direct') # 'direct' vagy 'helper'

    # Adatbázis adatok (közvetlen kapcsolathoz)
    db_host = db.Column(db.String(100))
    db_name = db.Column(db.String(100))
    db_user = db.Column(db.String(100))
    encrypted_db_pass = db.Column(db.LargeBinary)

    # FTP adatok
    ftp_type = db.Column(db.String(10), nullable=False, default='sftp')
    ftp_host = db.Column(db.String(100), nullable=False)
    ftp_user = db.Column(db.String(100), nullable=False)
    encrypted_ftp_pass = db.Column(db.LargeBinary)
    remote_path = db.Column(db.String(200), nullable=False)
    
    # Helper Plugin adatok
    helper_url = db.Column(db.String(255))
    encrypted_helper_api_key = db.Column(db.LargeBinary)

    # Mentési beállítások
    versions_to_keep = db.Column(db.Integer, default=3)
    backup_schedule = db.Column(db.String(50), nullable=False, default='manual') # 'manual', 'daily', 'weekly', 'monthly'

    # Állapot
    last_backup_time = db.Column(db.String(50), default='Soha')
    last_backup_status = db.Column(db.String(500), default='Nincs információ')

    def set_password(self, password, field):
        if password:
            encrypted_pass = cipher_suite.encrypt(password.encode())
            setattr(self, f"encrypted_{field}_pass", encrypted_pass)

    def get_password(self, field):
        encrypted_pass = getattr(self, f"encrypted_{field}_pass")
        if encrypted_pass:
            return cipher_suite.decrypt(encrypted_pass).decode()
        return ""

# --- A MENTÉSI LOGIKA KISZERVEZVE EGY KÜLÖN FÜGGVÉNYBE ---
def _run_backup_logic(project):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    project_backup_root = os.path.join('/backups', project.name)
    current_backup_path = os.path.join(project_backup_root, timestamp)
    
    os.makedirs(current_backup_path, exist_ok=True)
    
    # 1. Adatbázis mentés
    db_backup_file = os.path.join(current_backup_path, 'db_backup.sql')

    if project.backup_method == 'helper':
        # HELPER BŐVÍTMÉNYES MÓDSZER
        api_key = cipher_suite.decrypt(project.encrypted_helper_api_key).decode()
        trigger_url = f"{project.helper_url}?syryus_action=backup_db&api_key={api_key}"
        
        response = requests.get(trigger_url, timeout=120)
        response.raise_for_status()
        
        response_text = response.text
        if not response_text.startswith('SUCCESS:'):
            raise Exception(f"Helper plugin error: {response_text}")
            
        remote_file_name = response_text.split(':', 1)[1]
        
        ftp_pass = project.get_password('ftp')
        uploads_path = os.path.join(project.remote_path, 'wp-content', 'uploads')
        
        lftp_get_command = f"lftp -u '{project.ftp_user},{ftp_pass}' {project.ftp_type}://{project.ftp_host} -e 'get {uploads_path}/{remote_file_name} -o {db_backup_file}; quit'"
        subprocess.run(lftp_get_command, check=True, shell=True, stderr=subprocess.PIPE, text=True)
        
        lftp_rm_command = f"lftp -u '{project.ftp_user},{ftp_pass}' {project.ftp_type}://{project.ftp_host} -e 'rm {uploads_path}/{remote_file_name}; quit'"
        subprocess.run(lftp_rm_command, check=True, shell=True, stderr=subprocess.PIPE, text=True)
        
    else: # 'direct' módszer
        db_pass = project.get_password('db')
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
    db.session.commit()

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
            backup_method=request.form['backup_method'],
            db_host=request.form.get('db_host'),
            db_name=request.form.get('db_name'),
            db_user=request.form.get('db_user'),
            ftp_type=request.form['ftp_type'],
            ftp_host=request.form['ftp_host'],
            ftp_user=request.form['ftp_user'],
            remote_path=request.form['remote_path'],
            helper_url=request.form.get('helper_url'),
            versions_to_keep=int(request.form.get('versions_to_keep', 3)),
            backup_schedule=request.form['backup_schedule']
        )
        project.set_password(request.form.get('db_pass'), 'db')
        project.set_password(request.form.get('ftp_pass'), 'ftp')
        project.set_password(request.form.get('helper_api_key'), 'helper_api')
        
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
        project.backup_method=request.form['backup_method']
        project.db_host=request.form.get('db_host')
        project.db_name=request.form.get('db_name')
        project.db_user=request.form.get('db_user')
        project.ftp_type=request.form['ftp_type']
        project.ftp_host=request.form['ftp_host']
        project.ftp_user=request.form['ftp_user']
        project.remote_path=request.form['remote_path']
        project.helper_url=request.form.get('helper_url')
        project.versions_to_keep=int(request.form.get('versions_to_keep', 3))
        project.backup_schedule=request.form['backup_schedule']
        
        if request.form.get('db_pass'):
            project.set_password(request.form.get('db_pass'), 'db')
        if request.form.get('ftp_pass'):
            project.set_password(request.form.get('ftp_pass'), 'ftp')
        if request.form.get('helper_api_key'):
            project.set_password(request.form.get('helper_api_key'), 'helper_api')

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
    try:
        _run_backup_logic(project)
        flash(f"'{project.name}' mentése sikeres!", 'success')
    except Exception as e:
        error_message = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            error_message = e.stderr
        project.last_backup_status = f'Hiba: {error_message}'
        db.session.commit()
        flash(f"'{project.name}' mentése sikertelen! Hiba: {error_message}", 'danger')
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run()