from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'khoa_bi_mat_cho_session' # Cần thiết cho session
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_task.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS (CSDL) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='member')

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='Mới')
    due_date = db.Column(db.DateTime, nullable=True)
    logged_hours = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# --- AUTH DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Vui lòng đăng nhập!'}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- API ROUTES ---
@app.route('/')
def home():
    return render_template('dashboard.html')

# Đăng ký & Đăng nhập
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Tài khoản đã tồn tại'}), 400
    hashed_pw = generate_password_hash(data['password'])
    new_user = User(username=data['username'], password_hash=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'Đăng ký thành công!'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password_hash, data['password']):
        session['user_id'] = user.id
        session['username'] = user.username
        return jsonify({'message': 'Đăng nhập thành công'})
    return jsonify({'error': 'Sai thông tin'}), 401

@app.route('/api/logout')
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Đã đăng xuất'})

# Lấy Task & AI Cảnh báo
@app.route('/api/tasks', methods=['GET'])
@login_required
def get_tasks():
    tasks = Task.query.filter_by(user_id=session['user_id']).order_by(Task.id.desc()).all()
    output = []
    now = datetime.now()
    for t in tasks:
        # AI RULE: Cảnh báo trễ (Giai đoạn 3)
        is_risk = False
        if t.status != 'Hoàn thành' and t.due_date:
            delta = t.due_date - now
            if delta.days < 2:
                is_risk = True
        
        output.append({
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
            'logged_hours': t.logged_hours,
            'is_risk': is_risk
        })
    return jsonify(output)

# Tạo Task
@app.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    data = request.json
    due_date = datetime.strptime(data['due_date'], '%Y-%m-%d') if data['due_date'] else None
    new_task = Task(title=data['title'], due_date=due_date, user_id=session['user_id'])
    db.session.add(new_task)
    db.session.commit()
    return jsonify({'message': 'Tạo task thành công'})

# Update & AI Chấm công (ĐÃ SỬA LỖI THIẾU ID TẠI ĐÂY)
@app.route('/api/tasks/<int:id>', methods=['PUT'])
@login_required
def update_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != session['user_id']: return jsonify({'error': 'Không có quyền'}), 403
    
    data = request.json
    new_status = data.get('status')

    # AI RULE: Tự động chấm công (Giai đoạn 4)
    if new_status == 'Hoàn thành' and task.status != 'Hoàn thành':
        task.logged_hours += 2.0 
    
    if new_status: task.status = new_status
    db.session.commit()
    return jsonify({'message': 'Cập nhật xong'})

# Xóa Task (ĐÃ SỬA LỖI THIẾU ID TẠI ĐÂY)
@app.route('/api/tasks/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != session['user_id']: return jsonify({'error': 'Không có quyền'}), 403
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Đã xóa'})

# API Dữ liệu Biểu đồ
@app.route('/api/chart-data', methods=['GET'])
@login_required
def get_chart_data():
    tasks = Task.query.filter_by(user_id=session['user_id']).all()
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == 'Hoàn thành')
    total_hours = sum(t.logged_hours for t in tasks)
    return jsonify({
        'completed': completed,
        'pending': total - completed,
        'total_hours': total_hours
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)