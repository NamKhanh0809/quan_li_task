from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'SMART_TASK_KPI_KEY'

# CẤU HÌNH 2 DB RIÊNG BIỆT
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_BINDS'] = {
    'task_data': 'sqlite:///tasks.db'
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Task(db.Model):
    __bind_key__ = 'task_data'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(100), nullable=False)
    est_hours = db.Column(db.Float, nullable=False)
    actual_hours = db.Column(db.Float, default=0.0)
    due_date = db.Column(db.DateTime, nullable=False)
    task_type = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Todo')
    progress = db.Column(db.Integer, default=0)
    warning_date = db.Column(db.DateTime)
    is_risk = db.Column(db.Boolean, default=False)
    
    assignee_id = db.Column(db.Integer, nullable=True)
    penalized_user_id = db.Column(db.Integer, nullable=True)
    last_assignee_name = db.Column(db.String(50), nullable=True)
    
    assignee = None 

# --- HÀM HỖ TRỢ ---
def manual_join(tasks):
    users = User.query.all()
    user_map = {u.id: u for u in users}
    for t in tasks:
        if t.assignee_id and t.assignee_id in user_map:
            t.assignee = user_map[t.assignee_id]
        else:
            t.assignee = None

def run_ai_logic(task, user_map=None):
    now = datetime.now()
    if task.status != 'Done' and now > task.due_date:
        if task.status != 'Late':
            task.status = 'Late'
            user_name = "Unknown"
            if task.assignee_id and user_map and task.assignee_id in user_map:
                user_name = user_map[task.assignee_id].username
            task.penalized_user_id = task.assignee_id       
            task.last_assignee_name = user_name 
            flash(f"🚨 Task {task.code} quá hạn! Đã thu hồi.", "danger")
            task.assignee_id = None 
        return

    h = task.est_hours
    dw_days = h / 6 if h < 24 else 1.2 * (h / 4)
    task.warning_date = task.due_date - timedelta(days=dw_days)

    if now >= task.warning_date and task.progress < 50 and task.status != 'Done':
        task.is_risk = True
    else:
        task.is_risk = False

# --- DECORATORS ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'Admin': return "Chỉ Admin mới có quyền này", 403
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---
@app.route('/')
@login_required
def dashboard():
    user_id = session['user_id']
    role = session['role']
    
    tasks = Task.query.all()
    users = User.query.all()
    user_map = {u.id: u for u in users}

    for t in tasks: run_ai_logic(t, user_map)
    db.session.commit()
    manual_join(tasks)

    my_tasks = []      
    available_tasks = [] 
    member_data = {} 
    all_done_tasks = []

    # --- TÍNH TOÁN DỮ LIỆU BIỂU ĐỒ TRÒN (CHART DATA) ---
    # [Gray, Red, Green, Yellow] -> [Kho chung, Thu hồi, Done, Doing]
    chart_stats = [0, 0, 0, 0] 

    if role == 'Admin':
        # Admin: Thống kê toàn bộ hệ thống
        for t in tasks:
            if t.status == 'Late': 
                chart_stats[1] += 1 # Red: Thu hồi
            elif t.status == 'Done': 
                chart_stats[2] += 1 # Green: Done
            elif t.assignee_id is not None: 
                chart_stats[3] += 1 # Yellow: Doing (Đã có người nhận)
            else: 
                chart_stats[0] += 1 # Gray: Kho chung (Chưa ai nhận)

        # Logic Admin cũ (KPI...)
        all_done_tasks = [t for t in tasks if t.status == 'Done']
        all_done_tasks.sort(key=lambda x: x.id, reverse=True)
        all_members = [u for u in users if u.role == 'Member']
        for m in all_members:
            m_tasks = [t for t in tasks if t.assignee_id == m.id or t.penalized_user_id == m.id]
            m_tasks.sort(key=lambda x: (0 if x.status not in ['Done', 'Late'] else (1 if x.status == 'Done' else 2), not x.is_risk, x.due_date))
            total_done = sum(t.est_hours for t in m_tasks if t.status == 'Done' and t.assignee_id == m.id)
            penalty_val = sum(t.est_hours * 2 for t in tasks if t.penalized_user_id == m.id)
            member_data[m] = {'tasks': m_tasks, 'kpi': round(total_done - penalty_val, 1), 'penalty': round(penalty_val, 1)}

    else: # Member
        # Member: Chỉ thống kê task CỦA MÌNH
        for t in tasks:
            # Task đang làm hoặc đã xong của mình
            if t.assignee_id == user_id:
                if t.status == 'Done': chart_stats[2] += 1 # Green
                else: chart_stats[3] += 1 # Yellow (Doing)
            
            # Task mình làm hỏng (Bị thu hồi)
            if t.penalized_user_id == user_id:
                chart_stats[1] += 1 # Red
            
            # Member không quan tâm kho chung (Gray = 0)

    # Phân loại danh sách hiển thị
    for t in tasks:
        if t.assignee_id == user_id: my_tasks.append(t)
        elif t.assignee_id is None and t.status != 'Done': available_tasks.append(t)

    # Hàm sắp xếp
    def get_sort_priority(task):
        if task.status == 'Late': return 2
        if task.status == 'Done': return 1
        return 0
    my_tasks.sort(key=lambda x: (get_sort_priority(x), not x.is_risk, x.due_date))

    return render_template('dashboard.html', 
                           role=role, 
                           my_tasks=my_tasks, 
                           available_tasks=available_tasks,
                           member_data=member_data, 
                           all_done_tasks=all_done_tasks,
                           chart_stats=chart_stats, # Truyền dữ liệu biểu đồ sang HTML
                           now=datetime.now())

# --- CRUD & AUTH (Giữ nguyên) ---
@app.route('/create_task', methods=['POST'])
@admin_required
def create_task():
    code = request.form['code']
    if Task.query.filter_by(code=code).first():
        flash(f"❌ Mã {code} đã tồn tại!", "danger")
        return redirect(url_for('dashboard'))
    title = request.form['title']
    est = float(request.form['est_hours'])
    due = datetime.strptime(request.form['due_date'], '%Y-%m-%dT%H:%M')
    t_type = "Task Nhỏ" if est < 24 else "Task Lớn"
    db.session.add(Task(code=code, title=title, est_hours=est, due_date=due, task_type=t_type))
    db.session.commit()
    flash(f"✅ Đã tạo {code}", "success")
    return redirect(url_for('dashboard'))

@app.route('/create_member', methods=['POST'])
@admin_required
def create_member():
    username = request.form['username']
    if User.query.filter_by(username=username).first():
        flash("Tên tồn tại", "danger")
    else:
        db.session.add(User(username=username, password_hash=generate_password_hash(request.form['password']), role='Member'))
        db.session.commit()
        flash(f"✅ Đã tạo Member: {username}", "success")
    return redirect(url_for('dashboard'))

@app.route('/delete_member/<int:id>', methods=['POST'])
@admin_required
def delete_member(id):
    member = User.query.get_or_404(id)
    if member.role == 'Admin': return redirect(url_for('dashboard'))
    active_tasks = Task.query.filter_by(assignee_id=id).all()
    unfinished = [t for t in active_tasks if t.status not in ['Done', 'Late']]
    if unfinished:
        flash(f"⛔ {member.username} còn task đang làm!", "danger")
    else:
        for t in active_tasks:
            if t.status == 'Done': t.last_assignee_name = f"{member.username} (Đã xóa)"
            t.assignee_id = None 
        for t in Task.query.filter_by(penalized_user_id=id).all(): t.penalized_user_id = None
        db.session.delete(member)
        db.session.commit()
        flash(f"✅ Đã xóa nhân viên {member.username}.", "success")
    return redirect(url_for('dashboard'))

@app.route('/claim_task/<int:id>')
@login_required
def claim_task(id):
    if session['role'] == 'Admin': return redirect(url_for('dashboard'))
    task = Task.query.get(id)
    if task.assignee_id is None:
        task.assignee_id = session['user_id']
        task.status = 'Doing'
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/update_progress/<int:id>', methods=['POST'])
@login_required
def update_progress(id):
    task = Task.query.get(id)
    if task.assignee_id != session['user_id']: return "Lỗi", 403
    prog = int(request.form['progress'])
    task.progress = prog
    if prog == 100:
        task.status = 'Done'
        task.actual_hours = task.est_hours
        flash("🏆 Hoàn thành!", "success")
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user = User.query.get(session['user_id'])
    user.password_hash = generate_password_hash(request.form['new_password'])
    db.session.commit()
    flash("Đổi mật khẩu thành công", "success")
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        flash("Sai thông tin", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(role='Admin').first():
        db.session.add(User(username='admin', password_hash=generate_password_hash('admin123'), role='Admin'))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)