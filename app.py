import os
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user, login_required
import calendar
import secrets
from werkzeug.utils import secure_filename
import random

# Inisialisasi Aplikasi Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_123'

# Konfigurasi Database SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
    os.path.join(basedir, 'instance', 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inisialisasi Ekstensi
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Konfigurasi Upload Profil
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename):
    """Cek format file yang diizinkan"""
    return '.' in filename and filename.rsplit(
        '.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------- MODELS -----------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    bio = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True, default='default.png')
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    transactions = db.relationship('Transaction', backref='owner', lazy=True)

    def __init__(self, name, email, password, bio=None, phone=None, profile_image='default.png', reset_token=None, reset_token_expiry=None):
        self.name = name
        self.email = email
        self.password = password
        self.bio = bio
        self.phone = phone
        self.profile_image = profile_image
        self.reset_token = reset_token
        self.reset_token_expiry = reset_token_expiry

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'pemasukan' / 'pengeluaran'
    category = db.Column(db.String(50), nullable=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __init__(self, title, amount, type, date=None, category=None, owner=None, user_id=None):
        self.title = title
        self.amount = amount
        self.type = type
        if date is not None:
            self.date = date
        self.category = category
        if owner is not None:
            self.owner = owner
        if user_id is not None:
            self.user_id = user_id

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    deadline = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner = db.relationship('User', backref='wishlists', lazy=True)

    def __init__(self, title, target_amount, current_amount=0.0, deadline=None, user_id=None):
        self.title = title
        self.target_amount = target_amount
        self.current_amount = current_amount
        if deadline is not None:
            self.deadline = deadline
        if user_id is not None:
            self.user_id = user_id

class FinancialTip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    icon = db.Column(db.String(50), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ----------------- UTILS -----------------

def parse_amount(amount_str):
    """Membersihkan string mata uang ke float"""
    if not amount_str:
        return 0.0
    amount_str = str(amount_str).replace('.', '').replace(',', '')
    try:
        return float(amount_str)
    except ValueError:
        return 0.0

@app.template_filter('rupiah')
def rupiah_format(value):
    """Filter Jinja2 untuk format Rupiah"""
    try:
        return f"Rp {int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return value

# ----------------- ROUTES -----------------

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email sudah terdaftar.', 'error')
            return redirect(url_for('register'))
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(name=name, email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Registrasi Berhasil! Silakan Login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email, password = request.form.get('email'), request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('Login Berhasil!', 'success')
            return redirect(url_for('dashboard'))
        flash('Email atau password salah.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    today = datetime.now().date()
    first_day = today.replace(day=1)
    
    all_trans = Transaction.query.filter_by(user_id=current_user.id).all()
    overall_inc = sum(t.amount for t in all_trans if t.type == 'pemasukan')
    overall_exp = sum(t.amount for t in all_trans if t.type == 'pengeluaran')
    balance = overall_inc - overall_exp

    month_trans = [t for t in all_trans if t.date >= first_day]
    total_inc = sum(t.amount for t in month_trans if t.type == 'pemasukan')
    total_exp = sum(t.amount for t in month_trans if t.type == 'pengeluaran')
    avg_daily = total_exp / today.day if today.day > 0 else 0

    # Group expenses
    grouped_expenses_dict = defaultdict(list)
    for t in month_trans:
        if t.type == 'pengeluaran':
            grouped_expenses_dict[t.date].append(t)
    
    grouped_expenses = []
    for d in sorted(grouped_expenses_dict.keys(), reverse=True):
        grouped_expenses.append({
            'date': d,
            'transactions': grouped_expenses_dict[d],
            'daily_total': sum(t.amount for t in grouped_expenses_dict[d])
        })

    all_tips = FinancialTip.query.all()
    daily_tip = random.choice(all_tips) if all_tips else None

    # Simple Insights
    insights = []
    if total_exp > 0:
        cat_totals = defaultdict(float)
        for t in month_trans:
            if t.type == 'pengeluaran': cat_totals[t.category or 'Lainnya'] += t.amount
        if cat_totals:
            top_cat = max(cat_totals, key=cat_totals.get)
            if top_cat == 'Makan' and total_inc > 0 and cat_totals[top_cat] > total_inc * 0.4:
                insights.append({'icon': 'ph-fork-knife', 'color': 'rose', 'text': "Makanmu boros! Masak sendiri yuk."})
        if avg_daily > 50000:
            insights.append({'icon': 'ph-warning-circle', 'color': 'orange', 'text': "Rata-rata pengeluaran harian > 50rb."})
    
    if not insights:
        insights.append({'icon': 'ph-sparkle', 'color': 'emerald', 'text': "Keuangan stabil bulan ini!"})

    return render_template('dashboard.html', total_income=total_inc, total_expense=total_exp, 
                           balance=balance, avg_daily_expense=avg_daily, 
                           grouped_expenses=grouped_expenses, daily_tip=daily_tip, insights=insights)

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    title, amount_str, t_type, d_str, cat = request.form.get('title'), request.form.get('amount'), \
                                            request.form.get('type'), request.form.get('date'), \
                                            request.form.get('category', '').strip()
    amount = parse_amount(amount_str)
    try: date_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
    except Exception: date_obj = datetime.utcnow().date()

    if amount > 0:
        db.session.add(Transaction(title=title, amount=amount, type=t_type, date=date_obj, category=cat, owner=current_user))
        db.session.commit()
        flash('Transaksi Berhasil!', 'success')
    else: flash('Nominal tidak valid.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/history')
@login_required
def history():
    m_filter, t_filter = request.args.get('month'), request.args.get('type')
    query = Transaction.query.filter_by(user_id=current_user.id)
    if m_filter:
        try:
            y, m = map(int, m_filter.split('-'))
            start = datetime(y, m, 1).date()
            end = (datetime(y, m+1, 1) if m < 12 else datetime(y+1, 1, 1)).date() - timedelta(days=1)
            query = query.filter(Transaction.date >= start, Transaction.date <= end)
        except Exception: pass
    if t_filter in ['pemasukan', 'pengeluaran']: query = query.filter(Transaction.type == t_filter)
    
    trans = query.order_by(Transaction.date.desc()).all()
    
    def group_trans(t_list):
        d = defaultdict(list)
        for t in t_list: d[t.date].append(t)
        res = []
        for date in sorted(d.keys(), reverse=True):
            res.append({'date': date, 'transactions': d[date], 'daily_total': sum(tx.amount for tx in d[date])})
        return res

    return render_template('history.html', grouped_pemasukan=group_trans([t for t in trans if t.type == 'pemasukan']),
                           grouped_pengeluaran=group_trans([t for t in trans if t.type == 'pengeluaran']),
                           current_time=datetime.now())

@app.route('/edit_transaction/<int:trans_id>', methods=['POST'])
@login_required
def edit_transaction(trans_id):
    t = db.get_or_404(Transaction, trans_id)
    if t.owner == current_user:
        t.title, t.type, t.category = request.form.get('title'), request.form.get('type'), request.form.get('category')
        t.amount = parse_amount(request.form.get('amount'))
        try: t.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception: pass
        db.session.commit()
        flash('Berhasil diubah!', 'success')
    return redirect(url_for('history'))

@app.route('/delete_transaction/<int:trans_id>', methods=['POST'])
@login_required
def delete_transaction(trans_id):
    t = db.get_or_404(Transaction, trans_id)
    if t.owner == current_user:
        db.session.delete(t)
        db.session.commit()
        flash('Berhasil dihapus!', 'success')
    return redirect(url_for('history'))

@app.route('/report')
@login_required
def report():
    m_filter = request.args.get('month', datetime.now().strftime('%Y-%m'))
    try: y, m = map(int, m_filter.split('-'))
    except Exception: y, m = datetime.now().year, datetime.now().month
    
    _, last_d = calendar.monthrange(y, m)
    start, end = datetime(y, m, 1).date(), datetime(y, m, last_d).date()
    trans = Transaction.query.filter(Transaction.user_id == current_user.id, Transaction.date >= start, Transaction.date <= end).all()
    
    total_inc = sum(t.amount for t in trans if t.type == 'pemasukan')
    total_exp = sum(t.amount for t in trans if t.type == 'pengeluaran')
    
    # Trends
    labels, inc_d, exp_d, trend_d = [], [], [], []
    initial = sum(t.amount for t in Transaction.query.filter(Transaction.user_id == current_user.id, Transaction.date < start).all() if t.type == 'pemasukan') - \
              sum(t.amount for t in Transaction.query.filter(Transaction.user_id == current_user.id, Transaction.date < start).all() if t.type == 'pengeluaran')
    curr = initial
    for d_idx in range(1, last_d + 1):
        dt = datetime(y, m, d_idx).date()
        labels.append(dt.strftime('%d'))
        di = sum(t.amount for t in trans if t.date == dt and t.type == 'pemasukan')
        de = sum(t.amount for t in trans if t.date == dt and t.type == 'pengeluaran')
        inc_d.append(di); exp_d.append(de)
        curr += (di - de); trend_d.append(curr)

    today = datetime.now().date()
    if y == today.year and m == today.month:
        days_to_divide = today.day
    else:
        days_to_divide = last_d
    avg_daily_expense = total_exp / days_to_divide if days_to_divide > 0 else 0

    return render_template('report.html', total_income=total_inc, total_expense=total_exp, balance=total_inc-total_exp,
                           avg_daily_expense=avg_daily_expense,
                           total_trans=len(trans), month_filter=m_filter, labels=labels, income_data=inc_d, 
                           expense_data=exp_d, trend_data=trend_d, trans_json=[{'Tanggal': t.date.strftime('%Y-%m-%d'), 'Nama': t.title, 'Kategori': t.category, 'Jenis': t.type, 'Jumlah': t.amount} for t in trans])

@app.route('/api/chart_data')
@login_required
def chart_data():
    today = datetime.now().date()
    first, last = today.replace(day=1), (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    trans = Transaction.query.filter(Transaction.user_id == current_user.id, Transaction.date >= first, Transaction.date <= last).all()
    
    cat_totals = defaultdict(float)
    for t in [tx for tx in trans if tx.type == 'pengeluaran']: cat_totals[t.category or 'Lainnya'] += t.amount
    
    labels, inc_d, exp_d = [], [], []
    for d_idx in range(1, last.day + 1):
        dt = today.replace(day=d_idx)
        labels.append(dt.strftime('%d %b'))
        inc_d.append(sum(t.amount for t in trans if t.date == dt and t.type == 'pemasukan'))
        exp_d.append(sum(t.amount for t in trans if t.date == dt and t.type == 'pengeluaran'))

    return jsonify({'donut': {'labels': list(cat_totals.keys()) or ['N/A'], 'data': list(cat_totals.values()) or [0]},
                    'bar': {'labels': labels, 'income': inc_d, 'expense': exp_d}})

@app.route('/wishlist')
@login_required
def wishlist():
    wishlists = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.deadline.asc()).all()
    res = []
    for w in wishlists:
        prog = (w.current_amount / w.target_amount * 100) if w.target_amount > 0 else 0
        rem, days = max(0, w.target_amount - w.current_amount), (w.deadline - datetime.now().date()).days
        if prog >= 100: stat, advice = "Selesai", "Target Tercapai! 🎉"
        elif days <= 0: stat, advice = "Terlambat", "Segera penuhi sisa dana."
        else:
            if days < 7: stat, advice = "Mendesak", "Waktu hampir habis!"
            else: stat, advice = "On Track", "Terus menabung!"
        res.append({'obj': w, 'progress': round(min(prog, 100), 1), 'remaining': rem, 'days_left': days, 'status': stat, 'advice': advice, 'daily_needed': rem/days if days > 0 else rem, 'monthly_needed': rem/(days/30) if days >= 30 else rem})
    return render_template('wishlist.html', wishlists=res)

@app.route('/add_wishlist', methods=['POST'])
@login_required
def add_wishlist():
    t, target, curr, d_str = request.form.get('title'), parse_amount(request.form.get('target_amount')), parse_amount(request.form.get('current_amount')), request.form.get('deadline')
    if d_str:
        db.session.add(Wishlist(title=t, target_amount=target, current_amount=curr, deadline=datetime.strptime(d_str, '%Y-%m-%d').date(), user_id=current_user.id))
        db.session.commit()
        flash('Wishlist Ditambahkan!', 'success')
    return redirect(url_for('wishlist'))

@app.route('/update_wishlist_progress/<int:id>', methods=['POST'])
@login_required
def update_wishlist_progress(id):
    w = db.get_or_404(Wishlist, id)
    if w.user_id == current_user.id:
        w.current_amount += parse_amount(request.form.get('amount'))
        db.session.commit(); flash('Progres Diperbarui!', 'success')
    return redirect(url_for('wishlist'))

@app.route('/delete_wishlist/<int:id>', methods=['POST'])
@login_required
def delete_wishlist(id):
    w = db.get_or_404(Wishlist, id)
    if w.user_id == current_user.id:
        db.session.delete(w); db.session.commit(); flash('Dihapus!', 'success')
    return redirect(url_for('wishlist'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name, current_user.email, current_user.bio, current_user.phone = request.form.get('name'), request.form.get('email'), request.form.get('bio'), request.form.get('phone')
        file = request.files.get('profile_image')
        if file and allowed_file(file.filename):
            filename = secure_filename(f"u{current_user.id}_{file.filename}")
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.profile_image = filename
        db.session.commit(); flash('Profil Diperbarui!', 'success')
    return render_template('profile.html', total_transactions=len(current_user.transactions), total_wishlists=len(current_user.wishlists))

@app.route('/education')
@login_required
def education():
    cat = request.args.get('category')
    tips = FinancialTip.query.filter_by(category=cat).all() if cat and cat != 'Semua' else FinancialTip.query.all()
    return render_template('education.html', tips=tips, categories=['Hemat', 'Menabung', 'Budgeting', 'Anak Kos', 'Kuliah', 'Pengeluaran Harian'], active_category=cat or 'Semua')


if __name__ == '__main__':
    with app.app_context():
        os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
        db.create_all()
    app.run(debug=True)
