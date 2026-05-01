import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import os
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'calming_exam_prep_secret_key'
DATABASE = 'examprep_v2.db'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS subject (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            exam_date TEXT NOT NULL,
            syllabus_file TEXT,
            FOREIGN KEY (user_id) REFERENCES user (id)
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS topic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (subject_id) REFERENCES subject (id)
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS study_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            topic_id INTEGER NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES user (id),
            FOREIGN KEY (topic_id) REFERENCES topic (id)
        )''')
        db.commit()

if not os.path.exists(DATABASE):
    init_db()

def get_current_user_id():
    return session.get('user_id')

MOTIVATIONAL_QUOTES = [
    "Focus on progress, not perfection.",
    "You don't have to see the whole staircase, just take the first step.",
    "Breathe. You've got this.",
    "Small steps lead to big results.",
    "Stress is the gap between our expectation and reality. Let's close it with a plan.",
    "Your potential is endless.",
    "Consistency is the key to success.",
    "Take a break. Your mind needs to recharge.",
    "One chapter at a time. One topic at a time.",
    "Believe in yourself and all that you are."
]

STUDY_TIPS = [
    "Use the Pomodoro Technique: 25 mins study, 5 mins break.",
    "Explain what you've learned to someone else (or your pet!) to solidify it.",
    "Hydrate! Your brain needs water to function at its best.",
    "Review your notes within 24 hours of writing them.",
    "Break big topics into smaller, bite-sized tasks.",
    "Get at least 7-8 hours of sleep for memory consolidation."
]

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    user_id = session['user_id']
    
    if request.method == 'POST':
        name = request.form.get('subject_name')
        exam_date = request.form.get('exam_date')
        syllabus_text = request.form.get('syllabus_text')
        syllabus_file = request.files.get('syllabus_file')
        
        filename = None
        if syllabus_file and syllabus_file.filename != '':
            filename = secure_filename(syllabus_file.filename)
            syllabus_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            if not syllabus_text and filename.endswith('.txt'):
                try:
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'r') as f:
                        syllabus_text = f.read()
                except:
                    pass
        
        if name and exam_date:
            cursor = db.execute('INSERT INTO subject (user_id, name, exam_date, syllabus_file) VALUES (?, ?, ?, ?)', 
                                (user_id, name, exam_date, filename))
            subject_id = cursor.lastrowid
            
            if syllabus_text:
                topics = []
                for line in syllabus_text.split('\n'):
                    for part in line.split(','):
                        clean_topic = part.strip()
                        if clean_topic:
                            topics.append(clean_topic)
                            
                for t in topics:
                    db.execute('INSERT INTO topic (subject_id, name) VALUES (?, ?)', (subject_id, t))
            
            db.commit()
            
            # Automatically generate/update timetable
            generate_timetable_internal(user_id)
            
            flash(f'Successfully scheduled "{name}" and updated your plan!', 'success')
            return redirect(url_for('index'))

    # Get overall stats for the dashboard
    subject_count = db.execute('SELECT COUNT(*) FROM subject WHERE user_id = ?', (user_id,)).fetchone()[0]
    total_topics = db.execute('SELECT COUNT(*) FROM topic WHERE subject_id IN (SELECT id FROM subject WHERE user_id = ?)', (user_id,)).fetchone()[0]
    completed_topics = db.execute('SELECT COUNT(*) FROM topic WHERE completed = 1 AND subject_id IN (SELECT id FROM subject WHERE user_id = ?)', (user_id,)).fetchone()[0]
    
    # Check if a study plan exists
    has_plan = db.execute('SELECT COUNT(*) FROM study_plan WHERE user_id = ?', (user_id,)).fetchone()[0] > 0
    
    progress = int((completed_topics / total_topics) * 100) if total_topics > 0 else 0
    
    quote = random.choice(MOTIVATIONAL_QUOTES)
    tip = random.choice(STUDY_TIPS)
    
    return render_template('index.html', 
                           username=session.get('username'),
                           subject_count=subject_count,
                           has_plan=has_plan,
                           progress=progress,
                           quote=quote,
                           tip=tip)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        user = db.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        
        existing = db.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        if existing:
            flash('Username already exists. Please login.', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        db.execute('INSERT INTO user (username, password) VALUES (?, ?)', (username, hashed_password))
        db.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    return redirect(url_for('index'))

@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM study_plan WHERE topic_id IN (SELECT id FROM topic WHERE subject_id = ?)', (subject_id,))
    db.execute('DELETE FROM topic WHERE subject_id = ?', (subject_id,))
    db.execute('DELETE FROM subject WHERE id = ? AND user_id = ?', (subject_id, user_id))
    db.commit()
    return redirect(url_for('setup'))

def generate_timetable_internal(user_id):
    db = get_db()
    # Clear existing uncompleted plans to regenerate
    today_str = datetime.now().strftime('%Y-%m-%d')
    db.execute('DELETE FROM study_plan WHERE user_id = ? AND date >= ? AND completed = 0', (user_id, today_str))
    
    subjects = db.execute('SELECT * FROM subject WHERE user_id = ?', (user_id,)).fetchall()
    if not subjects:
        return False
        
    today = datetime.now().date()
    
    for s in subjects:
        exam_date = datetime.strptime(s['exam_date'], '%Y-%m-%d').date()
        days_left = (exam_date - today).days
        
        if days_left <= 0:
            days_left = 1
            
        topics = db.execute('SELECT id FROM topic WHERE subject_id = ? AND completed = 0', (s['id'],)).fetchall()
        topics_list = [t['id'] for t in topics]
        
        if not topics_list:
            continue
            
        random.shuffle(topics_list)
        days_pool = list(range(days_left))
        random.shuffle(days_pool)
        
        for i, t_id in enumerate(topics_list):
            day_offset = days_pool[i % len(days_pool)]
            study_date = (today + timedelta(days=day_offset)).strftime('%Y-%m-%d')
            db.execute('INSERT INTO study_plan (user_id, date, topic_id) VALUES (?, ?, ?)', 
                       (user_id, study_date, t_id))
    db.commit()
    return True

@app.route('/generate_timetable', methods=['POST'])
def generate_timetable():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for('login'))
    
    if generate_timetable_internal(user_id):
        flash('Timetable successfully generated!', 'success')
    else:
        flash('Please add subjects and syllabus topics first.', 'error')
        
    return redirect(url_for('timetable'))

@app.route('/timetable', methods=['GET'])
def timetable():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for('login'))
        
    db = get_db()
    
    plan_raw = db.execute('''
        SELECT sp.id as plan_id, sp.date, sp.completed, 
               t.name as topic_name, s.name as subject_name, s.exam_date
        FROM study_plan sp
        JOIN topic t ON sp.topic_id = t.id
        JOIN subject s ON t.subject_id = s.id
        WHERE sp.user_id = ? 
        ORDER BY sp.date ASC, s.name ASC
    ''', (user_id,)).fetchall()
    
    grouped_plan = {}
    for row in plan_raw:
        d = row['date']
        if d not in grouped_plan:
            grouped_plan[d] = []
        grouped_plan[d].append(row)
        
    subject_count = db.execute('SELECT COUNT(*) FROM subject WHERE user_id = ?', (user_id,)).fetchone()[0]
    return render_template('timetable.html', plan=grouped_plan, subject_count=subject_count)

@app.route('/mark_plan_completed/<int:plan_id>', methods=['POST'])
def mark_plan_completed(plan_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for('login'))
        
    db = get_db()
    db.execute('UPDATE study_plan SET completed = 1 WHERE id = ? AND user_id = ?', (plan_id, user_id))
    
    plan = db.execute('SELECT topic_id FROM study_plan WHERE id = ?', (plan_id,)).fetchone()
    if plan:
        db.execute('UPDATE topic SET completed = 1 WHERE id = ?', (plan['topic_id'],))
        
    db.commit()
    return redirect(request.referrer or url_for('timetable'))

@app.route('/progress')
def progress():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for('login'))
        
    db = get_db()
    
    subject_stats = db.execute('''
        SELECT s.name, 
               COUNT(t.id) as total_topics,
               SUM(CASE WHEN t.completed = 1 THEN 1 ELSE 0 END) as completed_topics
        FROM subject s
        LEFT JOIN topic t ON s.id = t.subject_id
        WHERE s.user_id = ?
        GROUP BY s.id
    ''', (user_id,)).fetchall()
    
    total = sum(s['total_topics'] for s in subject_stats)
    completed = sum((s['completed_topics'] or 0) for s in subject_stats)
    percentage = int((completed / total) * 100) if total > 0 else 0
    
    stats_list = []
    for ss in subject_stats:
        tt = ss['total_topics']
        ct = ss['completed_topics'] or 0
        rate = int((ct / tt) * 100) if tt > 0 else 0
        stats_list.append({
            'name': ss['name'],
            'total': tt,
            'completed': ct,
            'rate': rate
        })
                
    return render_template('progress.html', 
                           total=total, 
                           completed=completed, 
                           percentage=percentage,
                           subjects=stats_list)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)
