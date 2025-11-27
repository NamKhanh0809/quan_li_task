from app import app, db, User
from werkzeug.security import generate_password_hash

# Xóa DB cũ để tạo lại từ đầu cho sạch sẽ
import os
if os.path.exists("users.db"): os.remove("users.db")

# Chạy trong bối cảnh ứng dụng
with app.app_context():
    db.create_all() # Tạo bảng mới
    
    # Thay bằng email thật của bạn để nhận mã
    my_email = "namtran2005999@gmail.com" 
    
    hashed_pw = generate_password_hash('admin123')
    
    # Tạo Admin có email
    admin = User(username='admin', password_hash=hashed_pw, role='Admin', email=my_email)
    
    db.session.add(admin)
    db.session.commit()
    
    print(f"✅ Đã tạo Admin: admin / admin123")
    print(f"📧 Email nhận mã: {my_email}")