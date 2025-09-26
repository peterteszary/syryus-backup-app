from app import app, db

with app.app_context():
    print("Initializing database tables...")
    db.create_all()
    print("Database tables created successfully.")