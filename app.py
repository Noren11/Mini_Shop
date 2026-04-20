from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from datetime import datetime
from functools import wraps

app = Flask(__name__, static_folder='templates/static')
app.config["SECRET_KEY"] = "mini_shop_secret_key_2026"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///shop.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ======================== Database Models ========================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cart_items = db.relationship('CartItem', backref='user', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='user', lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(300), nullable=True)
    stock = db.Column(db.Integer, default=50)


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    product = db.relationship('Product')


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Pending')
    address = db.Column(db.Text, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    payment_method = db.Column(db.String(50), default='Cash on Delivery')
    payment_status = db.Column(db.String(50), default='Unpaid')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ======================== Decorators ========================

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            flash("Admin access required.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated


# ======================== Context Processor ========================

@app.context_processor
def inject_cart_count():
    if current_user.is_authenticated:
        count = CartItem.query.filter_by(user_id=current_user.id).count()
        cart_total_qty = db.session.query(db.func.sum(CartItem.quantity)).filter_by(user_id=current_user.id).scalar() or 0
        return {'cart_count': count, 'cart_total_qty': int(cart_total_qty)}
    return {'cart_count': 0, 'cart_total_qty': 0}


# ======================== Public Routes ========================

@app.route("/")
def home():
    products = Product.query.limit(6).all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template("index.html", products=products, categories=categories)


@app.route("/shop")
def shop():
    category = request.args.get('category', '')
    search = request.args.get('q', '')
    sort = request.args.get('sort', 'newest')

    query = Product.query

    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    if sort == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.id.desc())

    products = query.all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template("shop.html", products=products, categories=categories, selected_category=category, search=search, sort=sort)


@app.route("/product/<int:product_id>")
def product_details(product_id):
    product = db.get_or_404(Product, product_id)
    related = Product.query.filter_by(category=product.category).filter(Product.id != product.id).limit(4).all()
    return render_template("product_details.html", product=product, related=related)


# ======================== Auth Routes ========================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            flash("This email is already registered.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        is_admin = User.query.count() == 0

        new_user = User(
            name=name, email=email,
            password=hashed_password,
            is_admin=is_admin
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Welcome back!", "success")
            if getattr(user, 'is_admin', False):
                return redirect(url_for("dashboard"))
            return redirect(url_for("shop"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have logged out.", "info")
    return redirect(url_for("home"))


# ======================== Cart Routes ========================

@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = db.get_or_404(Product, product_id)
    existing = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()

    if existing:
        existing.quantity += 1
    else:
        item = CartItem(user_id=current_user.id, product_id=product_id, quantity=1)
        db.session.add(item)

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        cart_qty = db.session.query(db.func.sum(CartItem.quantity)).filter_by(user_id=current_user.id).scalar() or 0
        return jsonify({'success': True, 'cart_qty': int(cart_qty), 'message': f'{product.name} added to cart!'})

    flash(f"'{product.name}' added to cart!", "success")
    return redirect(request.referrer or url_for('shop'))


@app.route("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    subtotal = sum(item.product.price * item.quantity for item in items)
    shipping = 60 if subtotal > 0 else 0
    total = subtotal + shipping
    return render_template("cart.html", items=items, subtotal=subtotal, shipping=shipping, total=total)


@app.route("/update-cart/<int:item_id>", methods=["POST"])
@login_required
def update_cart(item_id):
    item = db.get_or_404(CartItem, item_id)
    if item.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for('cart'))

    action = request.form.get('action')
    if action == 'increase':
        item.quantity += 1
    elif action == 'decrease':
        if item.quantity > 1:
            item.quantity -= 1
        else:
            db.session.delete(item)

    db.session.commit()
    return redirect(url_for('cart'))


@app.route("/remove-from-cart/<int:item_id>")
@login_required
def remove_from_cart(item_id):
    item = db.get_or_404(CartItem, item_id)
    if item.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for('cart'))

    db.session.delete(item)
    db.session.commit()
    flash("Item removed from cart.", "info")
    return redirect(url_for('cart'))


# ======================== Checkout & Order Routes ========================

@app.route("/checkout")
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("Your cart is empty!", "warning")
        return redirect(url_for('shop'))

    subtotal = sum(item.product.price * item.quantity for item in items)
    shipping = 60
    total = subtotal + shipping
    return render_template("checkout.html", items=items, subtotal=subtotal, shipping=shipping, total=total)


@app.route("/place-order", methods=["POST"])
@login_required
def place_order():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("Your cart is empty!", "warning")
        return redirect(url_for('shop'))

    address = request.form.get('address', '')
    phone = request.form.get('phone', '')
    payment_method = request.form.get('payment_method', 'Cash on Delivery')

    if not address or not phone:
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for('checkout'))

    subtotal = sum(item.product.price * item.quantity for item in items)
    shipping = 60
    total = subtotal + shipping

    payment_status = 'Paid' if payment_method == 'Online Payment' else 'Unpaid'

    order = Order(
        user_id=current_user.id,
        total=total,
        address=address,
        phone=phone,
        payment_method=payment_method,
        payment_status=payment_status
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.product.price
        )
        db.session.add(order_item)
        if item.product.stock:
            item.product.stock = max(0, item.product.stock - item.quantity)
        db.session.delete(item)

    db.session.commit()
    flash("Order placed successfully! 🎉", "success")
    return redirect(url_for('order_success', order_id=order.id))


@app.route("/order-success/<int:order_id>")
@login_required
def order_success(order_id):
    order = db.get_or_404(Order, order_id)
    if order.user_id != current_user.id:
        return redirect(url_for('home'))
    return render_template("order_success.html", order=order)


@app.route("/my-orders")
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("my_orders.html", orders=orders)


@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    if order.user_id != current_user.id and not getattr(current_user, 'is_admin', False):
        flash("Unauthorized", "danger")
        return redirect(url_for('home'))
    return render_template("order_detail.html", order=order)


@app.route("/cancel-order/<int:order_id>")
@login_required
def cancel_order(order_id):
    order = db.get_or_404(Order, order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for('my_orders'))

    if order.status in ['Pending', 'Processing']:
        order.status = 'Cancelled'
        for oi in order.items:
            if oi.product and oi.product.stock is not None:
                oi.product.stock += oi.quantity
        db.session.commit()
        flash("Order cancelled successfully.", "info")
    else:
        flash("This order cannot be cancelled anymore.", "warning")

    return redirect(url_for('my_orders'))


# ======================== Admin Routes ========================

@app.route("/dashboard")
@login_required
@admin_required
def dashboard():
    products = Product.query.all()
    users = User.query.all()
    orders = Order.query.all()
    total_revenue = sum(o.total for o in orders if o.status not in ['Cancelled'])
    pending_orders = len([o for o in orders if o.status == 'Pending'])
    delivered_orders = len([o for o in orders if o.status == 'Delivered'])
    return render_template("dashboard.html",
        products=products, users=users, orders=orders,
        total_revenue=total_revenue, pending_orders=pending_orders,
        delivered_orders=delivered_orders
    )


@app.route("/customers")
@login_required
@admin_required
def customers():
    users = User.query.all()
    return render_template("customers.html", users=users)


@app.route("/admin/orders")
@login_required
@admin_required
def admin_orders():
    status_filter = request.args.get('status', '')
    query = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    orders = query.all()
    return render_template("admin_orders.html", orders=orders, selected_status=status_filter)


@app.route("/admin/update-order/<int:order_id>", methods=["POST"])
@login_required
@admin_required
def admin_update_order(order_id):
    order = db.get_or_404(Order, order_id)
    new_status = request.form.get('status')
    valid = ['Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled']
    if new_status in valid:
        old_status = order.status
        order.status = new_status
        if new_status == 'Delivered':
            order.payment_status = 'Paid'
        if new_status == 'Cancelled' and old_status != 'Cancelled':
            for oi in order.items:
                if oi.product and oi.product.stock is not None:
                    oi.product.stock += oi.quantity
        db.session.commit()
        flash(f"Order #{order.id} → {new_status}", "success")
    return redirect(url_for('admin_orders'))


@app.route("/add-product", methods=["GET", "POST"])
@login_required
@admin_required
def add_product():
    if request.method == "POST":
        new_product = Product(
            name=request.form["name"],
            description=request.form["description"],
            price=float(request.form["price"]),
            category=request.form["category"],
            image=request.form.get("image", ""),
            stock=int(request.form.get("stock", 50))
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product added successfully.", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_product.html")


@app.route("/edit-product/<int:product_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(product_id):
    product = db.get_or_404(Product, product_id)
    if request.method == "POST":
        product.name = request.form["name"]
        product.description = request.form["description"]
        product.price = float(request.form["price"])
        product.category = request.form["category"]
        product.image = request.form.get("image", "")
        product.stock = int(request.form.get("stock", product.stock or 50))
        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for("dashboard"))
    return render_template("edit_product.html", product=product)


@app.route("/delete-product/<int:product_id>")
@login_required
@admin_required
def delete_product(product_id):
    product = db.get_or_404(Product, product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "warning")
    return redirect(url_for("dashboard"))


# ======================== Main ========================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Auto-migrate: add new columns to existing tables
        with db.engine.connect() as conn:
            migrations = [
                ("SELECT is_admin FROM user LIMIT 1", "ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"),
                ("SELECT created_at FROM user LIMIT 1", "ALTER TABLE user ADD COLUMN created_at DATETIME"),
                ("SELECT stock FROM product LIMIT 1", "ALTER TABLE product ADD COLUMN stock INTEGER DEFAULT 50"),
            ]
            for check_sql, alter_sql in migrations:
                try:
                    conn.execute(text(check_sql))
                except Exception:
                    conn.execute(text(alter_sql))
                    conn.commit()

        # Make first user admin
        first_user = User.query.first()
        if first_user and not first_user.is_admin:
            first_user.is_admin = True
            db.session.commit()

    app.run(debug=True, use_reloader=False)