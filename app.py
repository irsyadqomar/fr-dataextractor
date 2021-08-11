import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import pymysql
import re
import io
import csv
from werkzeug.utils import secure_filename
import boto3
from filters import datetimeformat, file_type


S3_BUCKET                 = ("iqmscproject")
AWS_KEY                    = os.environ.get("AWS_ACCESS_KEY")
AWS_SECRET                 = os.environ.get("AWS_SECRET_KEY")
AWS_LOCATION               = 'http://{}.s3.amazonaws.com/'.format(S3_BUCKET)


s3 = boto3.client(
   "s3",
   aws_access_key_id=AWS_KEY,
   aws_secret_access_key=AWS_SECRET
)



app = Flask(__name__)
app.jinja_env.filters['datetimeformat'] = datetimeformat
app.jinja_env.filters['file_type'] = file_type

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = 'uploads/'
# These are the extension that we are accepting to be uploaded
app.config['ALLOWED_EXTENSIONS'] = set(['pdf', 'png', 'jpg', 'jpeg', 'JPG', 'PNG'])



# For a given file, return whether it's an allowed type or not
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']



app.config['SECRET_KEY'] = "secret"

connection = pymysql.connect(host= 'database-1.cuh6ukzu1onp.us-east-1.rds.amazonaws.com',
        user='admin',
        password='12345678',
        db='pythonlogin',
        cursorclass=pymysql.cursors.DictCursor)

@app.route('/login/', methods=['GET', 'POST'])
def login():
    # Output message if something goes wrong...
    msg = ''
    # Check if "username" and "password" POST requests exist (user submitted form)
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        # Create variables for easy access
        username = request.form['username']
        password = request.form['password']
        # Check if account exists using MySQL
        cursor=connection.cursor()
        cursor.execute('SELECT * FROM accounts WHERE username = %s AND password = %s', (username, password,))
        connection.commit()
        # Fetch one record and return result
        account = cursor.fetchone()
        # If account exists in accounts table in out database
        if account:
            # Create session data, we can access this data in other routes
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            # Redirect to home page
            return redirect(url_for('home'))
        else:
            # Account doesnt exist or username/password incorrect
            msg = 'Incorrect username/password!'
    # Show the login form with message (if any)
    return render_template('index.html', msg=msg)


@app.route('/login/logout')
def logout():
    # Remove session data, this will log the user out
   session.pop('loggedin', None)
   session.pop('id', None)
   session.pop('username', None)
   # Redirect to login page
   return redirect(url_for('login'))


@app.route('/login/register', methods=['GET', 'POST'])
def register():
    # Output message if something goes wrong...
    msg = ''
    # Check if "username", "password" and "email" POST requests exist (user submitted form)
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
        # Create variables for easy access
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        # Check if account exists using MySQL
        cursor=connection.cursor()
        cursor.execute('SELECT * FROM accounts WHERE username = %s', (username,))
        connection.commit()
        account = cursor.fetchone()
        # If account exists show error and validation checks
        if account:
            msg = 'Account already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address!'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers!'
        elif not username or not password or not email:
            msg = 'Please fill out the form!'
        else:
            # Account doesnt exists and the form data is valid, now insert new account into accounts table
            cursor.execute('INSERT INTO accounts VALUES (NULL, %s, %s, %s)', (username, password, email,))
            connection.commit()
            msg = 'You have successfully registered!'
    elif request.method == 'POST':
        # Form is empty... (no POST data)
        msg = 'Please fill out the form!'
    # Show registration form with message (if any)
    return render_template('register.html', msg=msg)

# http://localhost:5000/login/home - this will be the home page, only accessible for loggedin users
@app.route('/login/home')
def home():
    # Check if user is loggedin
    if 'loggedin' in session:
        # User is loggedin show them the home page
        s3_resource = boto3.resource('s3')
        my_bucket = s3_resource.Bucket(S3_BUCKET)
        summaries = my_bucket.objects.all()

        return render_template('home.html', username=session['username'], my_bucket=my_bucket, files=summaries)
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


@app.route('/login/profile')
def profile():
    # Check if user is loggedin
    if 'loggedin' in session:
        # We need all the account info for the user so we can display it on the profile page
        cursor=connection.cursor()
        cursor.execute('SELECT * FROM accounts WHERE id = %s', (session['id'],))
        connection.commit()
        account = cursor.fetchone()
        # Show the profile page with account info
        return render_template('profile.html', account=account)
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))

@app.route('/login/report')
def report():
    # Check if user is loggedin
    if 'loggedin' in session:
        return render_template('report.html')
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect(url_for('home'))


@app.route('/upload', methods=['post'])
def upload():
    if request.method == 'POST':
        img = request.files['file']
        if img:
                filename = secure_filename(img.filename)
                img.save(filename)
                s3.upload_file(
                    Bucket = S3_BUCKET,
                    Filename=filename,
                    Key = filename
                )
                flash('File uploaded successfully')
    return redirect(url_for('home'))




@app.route('/download', methods=['POST'])
def download():
    key = request.form['key']

    s3_resource = boto3.resource('s3')
    my_bucket = s3_resource.Bucket(S3_BUCKET)

    file_obj = my_bucket.Object(key).get()

    return Response(
        file_obj['Body'].read(),
        mimetype='text/plain',
        headers={"Content-Disposition": "attachment;filename={}".format(key)}
    )


@app.route('/download/report/csv')
def download_report():

    try:
        cursor = connection.cursor()

        cursor.execute("SELECT id, document, description, note, currentvalue, previousvalue FROM data")
        connection.commit()
        result = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        line = ['Id, Document, Description, Note, Current Value, Previous Value']
        writer.writerow(line)

        for row in result:
            line = [str(row['id']) + ',' + row['document'] + ',' + row['description'] + ',' + row['note'] + ',' + row['currentvalue'] + ',' + row['previousvalue']]
            writer.writerow(line)

        output.seek(0)

        return Response(output, mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=report.csv"})
    except Exception as e:
        print(e)




if __name__ == '__main__':
    app.run(debug=True)

