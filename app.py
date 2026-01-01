from flask import session
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import uuid
import sqlite3


app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production

#
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

TIME_SLOTS = [
    "10:00", "11:00", "12:00",
    "13:00", "14:00", "15:00",
    "16:00", "17:00"
]

@app.route('/slot-status')
def slot_status():
    date = request.args.get('date')

    conn = get_db_connection()
    rows = conn.execute(
        "SELECT time FROM appointments WHERE date = ?",
        (date,)
    ).fetchall()
    conn.close()

    booked = [r['time'] for r in rows]

    result = []
    for t in TIME_SLOTS:
        result.append({
            "time": t,
            "status": "booked" if t in booked else "available"
        })

    return jsonify(result)

@app.route('/available-times')
def available_times():
    date = request.args.get('date')

    conn = get_db_connection()
    booked = conn.execute(
        "SELECT time FROM appointments WHERE date = ?",
        (date,)
    ).fetchall()
    conn.close()

    booked_times = [row['time'] for row in booked]
    available = [t for t in TIME_SLOTS if t not in booked_times]

    return jsonify({"available": available})

def get_db_connection():
    conn = sqlite3.connect('appointments.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        service TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
""")


    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('appointments_view'))
        else:
            error = "Invalid username or password"

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password, phone) VALUES (?, ?, ?, ?)",
                (name, email, password, phone)
            )
            conn.commit()
            return redirect(url_for('customer_login'))
        except sqlite3.IntegrityError:
            error = "Email already registered"
        finally:
            conn.close()

    return render_template('register.html', error=error)

@app.route('/customer-login', methods=['GET', 'POST'])
def customer_login():
    error = None

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session['customer_logged_in'] = True
            session['user_id'] = user['id']
            return redirect(url_for('book'))
        else:
            error = "Invalid email or password"

    return render_template('customer_login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/book', methods=['GET', 'POST'])
def book():
    # Customer login required
    if not session.get('customer_logged_in'):
        return redirect(url_for('customer_login'))

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        service = request.form['service']
        date = request.form['date']
        time = request.form['time']

        appointment_id = str(uuid.uuid4())
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()

        # 🔐 IMPORTANT CHECK: prevent double booking
        existing = conn.execute(
            "SELECT 1 FROM appointments WHERE date = ? AND time = ?",
            (date, time)
        ).fetchone()

        if existing:
            conn.close()
            error = (
                "The selected time slot is no longer available. "
                "Please choose another available slot."
            )
            return render_template(
                'book.html',
                error=error,
                now=datetime.now().strftime('%Y-%m-%d')
            )

        # ✅ If slot is free, insert appointment
        conn.execute("""
            INSERT INTO appointments 
            (id, user_id, name, phone, service, date, time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            appointment_id,
            session['user_id'],
            name,
            phone,
            service,
            date,
            time,
            created_at
        ))
        conn.commit()
        conn.close()

        return redirect(url_for('confirmation', appointment_id=appointment_id))

    # GET request
    return render_template(
        'book.html',
        now=datetime.now().strftime('%Y-%m-%d')
    )
    
@app.route('/confirmation/<appointment_id>')
def confirmation(appointment_id):
    conn = get_db_connection()
    appointment = conn.execute(
        "SELECT * FROM appointments WHERE id = ?",
        (appointment_id,)
    ).fetchone()
    conn.close()

    if not appointment:
        return redirect(url_for('home'))

    return render_template('confirmation.html', appointment=appointment)


@app.route('/appointments')
def appointments_view():
    # Login protection
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # Database se appointments lana
    conn = get_db_connection()
    appointments = conn.execute("""
        SELECT * FROM appointments
        ORDER BY date, time
    """).fetchall()
    conn.close()

    return render_template(
        'appointments.html',
        appointments=appointments
    )


@app.route('/cancel/<appointment_id>')
def cancel_appointment(appointment_id):
    global appointments
    conn = get_db_connection()
    conn.execute(
     "DELETE FROM appointments WHERE id = ?",
    (appointment_id,)
)
    conn.commit()
    conn.close()

    return redirect(url_for('appointments_view'))

@app.route('/my-appointments')
def my_appointments():
    if not session.get('customer_logged_in'):
        return redirect(url_for('customer_login'))

    conn = get_db_connection()
    appointments = conn.execute(
        "SELECT * FROM appointments WHERE user_id = ? ORDER BY date, time",
        (session['user_id'],)
    ).fetchall()
    conn.close()

    return render_template('appointments.html', appointments=appointments)


if __name__ == '__main__':
    app.run(debug=True)  

