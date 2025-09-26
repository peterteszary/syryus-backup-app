#!/bin/sh

echo "-------------------------------------------"
echo "--- SYRYUS DIAGNOSTIC ENTRYPOINT START  ---"
echo "-------------------------------------------"
echo " "
echo ">> Running as user: $(whoami)"
echo " "

echo ">> STEP 1: Checking permissions of parent directory [/app]"
ls -ld /app
echo " "

echo ">> STEP 2: Attempting to create directory [/app/instance]"
mkdir -p /app/instance
if [ $? -eq 0 ]; then
    echo "SUCCESS: Directory /app/instance created or already exists."
else
    echo "FAILURE: Could not create /app/instance directory. Exiting."
    exit 1
fi
echo " "

echo ">> STEP 3: Checking final permissions of [/app/instance]"
ls -ld /app/instance
echo " "

echo ">> STEP 4: Attempting to create a simple test file"
touch /app/instance/test_file.txt
if [ $? -eq 0 ]; then
    echo "SUCCESS: test_file.txt created in /app/instance."
else
    echo "FAILURE: Could not create test_file.txt. This is likely the root cause."
fi
echo " "

echo ">> STEP 5: Running Database Initializer (init_db.py)"
python init_db.py
DB_INIT_EXIT_CODE=$?
echo " "

echo ">> STEP 6: Checking contents of /app/instance after init script"
ls -l /app/instance
echo " "

if [ $DB_INIT_EXIT_CODE -ne 0 ]; then
    echo "!!! CRITICAL FAILURE: Database initializer failed. Gunicorn will not be started."
    echo "-------------------------------------------"
    exit 1
fi

echo ">> STEP 7: Starting Gunicorn Web Server..."
echo "-------------------------------------------"
exec gunicorn --workers 1 --timeout 120 --bind 0.0.0.0:5000 app:app