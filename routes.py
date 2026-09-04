import time

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from models import Order, Product, User

routes = Blueprint("routes", __name__)


@routes.get("/")
def home():
    return redirect(url_for("routes.products"))


def payload():
    return request.get_json(silent=True) or request.form


def integer(data, key, default=None):
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default


def user_id():
    return session.get("user_id")


def log_event(level, message, **fields):
    getattr(current_app.logger, level)(message, extra={"fields": fields})


def authenticate(data):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    with current_app.session_factory() as db:
        return db.scalar(select(User).where(User.username == username, User.password == password))


@routes.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    data = payload()
    user = authenticate(data)
    if not user:
        log_event("warning", "login_failed", endpoint=request.endpoint, status=401, username=data.get("username", ""))
        current_app.metrics.increment("login.failure", {"endpoint": request.endpoint, "status": 401})
        if request.is_json:
            return jsonify(error="invalid credentials"), 401
        return render_template("login.html", error="Invalid credentials"), 401
    session["user_id"] = user.id
    log_event("info", "login_succeeded", endpoint=request.endpoint, status=200, user_id=user.id)
    current_app.metrics.increment("login.success", {"endpoint": request.endpoint, "status": 200})
    if request.is_json:
        return jsonify(message="logged in", user_id=user.id)
    return redirect(url_for("routes.products"))


@routes.post("/api/login")
def api_login():
    return login()


def product_data(product):
    return {"id": product.id, "name": product.name, "price": float(product.price)}


@routes.get("/products")
def products():
    with current_app.session_factory() as db:
        items = db.scalars(select(Product).order_by(Product.id)).all()
    return render_template("products.html", products=items, logged_in=user_id() is not None)


@routes.get("/api/products")
def api_products():
    with current_app.session_factory() as db:
        return jsonify(products=[product_data(item) for item in db.scalars(select(Product).order_by(Product.id)).all()])


def checkout_response():
    data = payload()
    current_user_id = user_id()
    product_id = integer(data, "product_id")
    quantity = integer(data, "quantity", 1)
    if not current_user_id or not product_id or quantity < 1:
        current_app.metrics.increment("checkout.failure", {"endpoint": request.endpoint, "status": 400})
        log_event("warning", "checkout_failed", endpoint=request.endpoint, status=400, user_id=current_user_id)
        return jsonify(error="login, product_id, and a positive quantity are required"), 400
    try:
        with current_app.session_factory() as db:
            product = db.get(Product, product_id)
            if not product:
                current_app.metrics.increment("checkout.failure", {"endpoint": request.endpoint, "status": 404})
                log_event("warning", "checkout_failed", endpoint=request.endpoint, status=404, user_id=current_user_id)
                return jsonify(error="product not found"), 404
            order = Order(user_id=current_user_id, product_id=product.id, quantity=quantity)
            db.add(order)
            db.commit()
            order_id = order.id
        current_app.metrics.increment("checkout.success", {"endpoint": request.endpoint, "status": 201})
        log_event("info", "checkout_succeeded", endpoint=request.endpoint, status=201, user_id=current_user_id, order_id=order_id)
        return jsonify(order_id=order_id, product=product_data(product), quantity=quantity), 201
    except SQLAlchemyError:
        current_app.logger.exception("database_error", extra={"fields": {"endpoint": request.endpoint, "status": 500, "user_id": current_user_id}})
        current_app.metrics.increment("checkout.failure", {"endpoint": request.endpoint, "status": 500})
        return jsonify(error="database error"), 500


@routes.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "GET":
        return render_template("checkout.html", logged_in=user_id() is not None)
    response = checkout_response()
    if request.is_json:
        return response
    status = response[1] if isinstance(response, tuple) else response.status_code
    return redirect(url_for("routes.products")) if status < 400 else response


@routes.post("/api/checkout")
def api_checkout():
    return checkout_response()


@routes.get("/api/health")
def health():
    try:
        with current_app.session_factory() as db:
            db.execute(text("SELECT 1"))
        return jsonify(status="ok")
    except SQLAlchemyError:
        current_app.logger.exception("database_error", extra={"fields": {"endpoint": request.endpoint, "status": 503}})
        return jsonify(status="unhealthy"), 503


@routes.get("/api/slow")
def slow():
    time.sleep(3)
    return jsonify(status="slow response")


@routes.get("/api/error")
def error():
    raise RuntimeError("intentional MiniShop error")