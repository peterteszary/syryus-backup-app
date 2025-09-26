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


# --- ADATBÁZIS MODELL (JAVÍTVA) ---
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    backup_method = db.Column(db.String(50), nullable=False, default='direct')
    db_host = db.Column(db.String(100))
    db_name = db.Column(db.String(100))
    db_user = db.Column(db.String(100))
    encrypted_db_pass = db.Column(db.LargeBinary)
    ftp_type = db.Column(db.String(10), nullable=False, default='sftp')
    ftp_host = db.Column(db.String(100), nullable=False)
    ftp_user = db.Column(db.String(100), nullable=False)
    encrypted_ftp_pass = db.Column(db.LargeBinary)
    remote_path = db.Column(db.String(200), nullable=False)
    helper_url = db.Column(db.String(255))
    # --- JAVÍTÁS ITT: A változónév most már konzisztens ---
    encrypted_helper_api_pass = db.Column(db.LargeBinary)
    versions_to_keep = db.Column(db.Integer, default=3)
    backup_schedule = db.Column(db.String(50), nullable=False, default='manual')
    last_backup_time = db.Column(db.String(50), default='Soha')
    last_backup_status = db.Column(db.String(500), default='Nincs információ')

    def set_password(self, password, field):
        if password:
            encrypted_pass = cipher_suite.encrypt(password.encode())
            setattr(self, f"encrypted_{field}_pass", encrypted_pass)

    def get_password(self, field):
        encrypted_pass = getattr(self, f"encrypted_{field}_pass", None)
        if encrypted_pass:
            return cipher_suite.decrypt(encrypted_pass).decode()
        return ""

# --- MENTÉSI LOGIKA (Változatlan, de most már helyes adatokkal dolgozik) ---
def _run_backup_logic(project):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    project_backup_root = os.path.join('/backups', project.name)
    current_backup_path = os.path.join(project_backup_root, timestamp)
    
    os.makedirs(current_backup_path, exist_ok=True)
    
    db_backup_file = os.path.join(current_backup_path, 'db_backup.sql')

    if project.backup_method == 'helper':
        api_key = project.get_password('helper_api')
        if not api_key or not project.helper_url:
            raise Exception("Helper URL or API Key is missing for this project.")
            
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
    else:
        db_pass = project.get_password('db')
        db_command = f"mysqldump --host={project.db_host} --user={project.db_user} --password='{db_pass}' {project.db_name} > {db_backup_file}"
        subprocess.run(db_command, check=True, shell=True, stderr=subprocess.PIPE, text=True)

    ftp_pass = project.get_password('ftp')
    files_backup_path = os.path.join(current_backup_path, 'files')
    lftp_command = f"lftp -u '{project.ftp_user},{ftp_pass}' {project.ftp_type}://{project.ftp_host} -e 'mirror --delete-first --verbose {project.remote_path} {files_backup_path}; quit'"
    subprocess.run(lftp_command, check=True, shell=True, stderr=subprocess.PIPE, text=True)

    all_backups = sorted([d for d in os.listdir(project_backup_root) if os.path.isdir(os.path.join(project_backup_root, d))], reverse=True)
    for old_backup in all_backups[project.versions_to_keep:]:
        subprocess.run(['rm', '-rf', os.path.join(project_backup_root, old_backup)])

    project.last_backup_time = timestamp
    project.last_backup_status = 'Sikeres'
    db.session.commit()

# --- FORM KEZELÉS (Változatlan, de most már a helyes mezőket kezeli) ---
def validate_and_save_project(project, is_new=False):
    form_data = request.form
    project.name = form_data['name']
    project.backup_method = form_data['backup_method']
    project.ftp_type = form_data['ftp_type']
    project.ftp_host = form_data['ftp_host']
    project.ftp_user = form_data['ftp_user']
    project.remote_path = form_data['remote_path']
    project.versions_to_keep = int(form_data.get('versions_to_keep', 3))
    project.backup_schedule = form_data['backup_schedule']

    if project.backup_method == 'direct':
        project.db_host = form_data.get('db_host')
        project.db_name = form_data.get('db_name')
        project.db_user = form_data.get('db_user')
        if not all([project.db_host, project.db_name, project.db_user]):
            flash('Közvetlen kapcsolat módnál minden DB adat kitöltése kötelező!', 'danger')
            return False
    else:
        project.helper_url = form_data.get('helper_url')
        if not project.helper_url:
            flash('Helper Bővítmény módnál a WordPress URL kitöltése kötelező!', 'danger')
            return False

    if is_new and not form_data.get('ftp_pass'):
         flash('Új projektnél az FTP jelszó megadása kötelező!', 'danger')
         return False
    project.set_password(form_data.get('ftp_pass'), 'ftp')
    
    if project.backup_method == 'direct':
        if is_new and not form_data.get('db_pass'):
            flash('Új projektnél a DB jelszó megadása kötelező!', 'danger')
            return False
        project.set_password(form_data.get('db_pass'), 'db')
    else:
        if is_new and not form_data.get('helper_api_key'): # A form mező neve maradhat _key
            flash('Új projektnél a Helper API kulcs megadása kötelező!', 'danger')
            return False
        project.set_password(form_data.get('helper_api_key'), 'helper_api') # Ez most már helyesen az 'encrypted_helper_api_pass' mezőt fogja írni

    if is_new:
        db.session.add(project)
    db.session.commit()
    return True

# --- WEB OLDALAK (Változatlan) ---
@app.route('/')
def index():
    # ...
# ... a fájl többi része változatlan ...