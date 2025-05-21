from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=True)  # Auto-approve for demo
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='user', lazy=True)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    rating = db.Column(db.Float, default=0.0)
    image_url = db.Column(db.String(300))
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='book', lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='Pending')

# Create tables and add admin user
with app.app_context():
    db.create_all()
    
    # Create admin user if not exists
    admin_user = User.query.filter_by(username='dhruba').first()
    if not admin_user:
        hashed_password = generate_password_hash('dhruba123')
        admin_user = User(
            username='dhruba',
            email='dhruba@admin.com',
            password=hashed_password,
            is_admin=True,
            is_approved=True
        )
        db.session.add(admin_user)
        db.session.commit()

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Authentication decorators
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        if not session.get('is_admin', False):
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# Routes
@app.route('/')
def index():
    featured_books = Book.query.order_by(Book.rating.desc()).limit(4).all()
    return render_template('index.html', featured_books=featured_books)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            if not user.is_approved and not user.is_admin:
                flash('Your account is pending approval', 'warning')
                return redirect(url_for('login'))
            
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('admin_dashboard' if user.is_admin else 'user_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            email=email,
            password=hashed_password,
            is_admin=False,
            is_approved=True  # Auto-approve for demo
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! You can now login.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    pending_users = User.query.filter_by(is_approved=False).all()
    books = Book.query.all()
    orders = Order.query.all()
    return render_template('admin/dashboard.html', 
                         pending_users=pending_users, 
                         books=books, 
                         orders=orders)

@app.route('/admin/approve-user/<int:user_id>')
@admin_required
def approve_user(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_approved = True
        db.session.commit()
        flash(f'User {user.username} approved successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add-book', methods=['GET', 'POST'])
@admin_required
def add_book():
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        description = request.form.get('description')
        price = float(request.form.get('price', 0))
        rating = float(request.form.get('rating', 0))
        image_url = None
        
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f"uploads/{filename}"
        
        new_book = Book(
            title=title,
            author=author,
            description=description,
            price=price,
            rating=rating,
            image_url=image_url
        )
        db.session.add(new_book)
        db.session.commit()
        flash('Book added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/add_book.html')

@app.route('/books')
def book_catalog():
    books = Book.query.all()
    return render_template('books/catalog.html', books=books)

@app.route('/books/<int:book_id>')
def book_details(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template('books/details.html', book=book)

@app.route('/order/<int:book_id>', methods=['POST'])
@login_required
def place_order(book_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    book = Book.query.get(book_id)
    if not book:
        flash('Book not found', 'danger')
        return redirect(url_for('book_catalog'))
    
    new_order = Order(
        user_id=session['user_id'],
        book_id=book_id,
        status='Pending'
    )
    db.session.add(new_order)
    db.session.commit()
    
    flash(f'Order placed for {book.title}!', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    user_orders = Order.query.filter_by(user_id=session['user_id']).all()
    return render_template('user/dashboard.html', orders=user_orders)

if __name__ == '__main__':
    app.run(debug=True)