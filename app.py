import os
from datetime import datetime
from decimal import Decimal

from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required, current_user
)
from flask_wtf import CSRFProtect, FlaskForm
from flask_wtf.csrf import generate_csrf
from wtforms import StringField, SubmitField, DecimalField, IntegerField
from wtforms.validators import DataRequired, Email, Length, Optional, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import event
from sqlalchemy.engine import Engine

# ----- Extensiones -----
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()
    except Exception:
        pass


def create_app():
    """Crea y configura la aplicación Flask.
    - Config simple y segura
    - SQLite en carpeta instance/
    - CSRF habilitado
    - Login redirige a /login cuando no autenticado
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
    app.config["WTF_CSRF_ENABLED"] = True

    os.makedirs(app.instance_path, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"
    csrf.init_app(app)

    app.jinja_env.globals.update(datetime=datetime)

    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf)

    # ----- Permisos por rol -----
    def roles_required(*roles):
        """Permite acceder solo si el rol del usuario está en roles; si no, 403."""
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                if not current_user.is_authenticated or current_user.role not in roles:
                    abort(403)
                return fn(*args, **kwargs)
            return wrapper
        return decorator

    # =====================
    #       MODELOS
    # =====================
    class User(db.Model, UserMixin):
        __tablename__ = "usuarios"
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(120), unique=True, nullable=False)
        password_hash = db.Column(db.String(255), nullable=False)
        role = db.Column(db.String(20), default="user")

        def set_password(self, raw_password: str):
            self.password_hash = generate_password_hash(raw_password)

        def check_password(self, raw_password: str) -> bool:
            return check_password_hash(self.password_hash, raw_password)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    class Cliente(db.Model):
        __tablename__ = "clientes"
        id = db.Column(db.Integer, primary_key=True)
        nombre = db.Column(db.String(120), nullable=False)
        direccion = db.Column(db.String(200))
        telefono = db.Column(db.String(50))
        email = db.Column(db.String(120))
        facturas = db.relationship("Factura", back_populates="cliente", lazy="dynamic")

        def __repr__(self):
            return f"<Cliente {self.id} - {self.nombre}>"

    class Producto(db.Model):
        __tablename__ = "productos"
        id = db.Column(db.Integer, primary_key=True)
        descripcion = db.Column(db.String(200), nullable=False)
        precio = db.Column(db.Numeric(10, 2), nullable=False, default=0)
        stock = db.Column(db.Integer, nullable=False, default=0)

        __table_args__ = (
            db.CheckConstraint("precio >= 0", name="ck_producto_precio_nonneg"),
            db.CheckConstraint("stock >= 0", name="ck_producto_stock_nonneg"),
        )

        detalles = db.relationship("DetalleFactura", back_populates="producto")

        def __repr__(self):
            return f"<Producto {self.id} - {self.descripcion} ${self.precio} stock:{self.stock}>"

    class Factura(db.Model):
        __tablename__ = "facturas"
        id = db.Column(db.Integer, primary_key=True)
        cliente_id = db.Column(
            db.Integer, db.ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False
        )
        fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

        cliente = db.relationship("Cliente", back_populates="facturas")
        detalles = db.relationship(
            "DetalleFactura",
            back_populates="factura",
            cascade="all, delete-orphan",
        )

        def recalcular_total(self):
            self.total = sum((d.subtotal or Decimal("0")) for d in self.detalles)

        def __repr__(self):
            return f"<Factura {self.id} cliente:{self.cliente_id} total:{self.total}>"

    class DetalleFactura(db.Model):
        __tablename__ = "detalle_factura"
        id = db.Column(db.Integer, primary_key=True)
        factura_id = db.Column(
            db.Integer, db.ForeignKey("facturas.id", ondelete="CASCADE"), nullable=False
        )
        producto_id = db.Column(
            db.Integer, db.ForeignKey("productos.id", ondelete="RESTRICT"), nullable=False
        )
        cantidad = db.Column(db.Integer, nullable=False, default=1)
        precio_unitario = db.Column(db.Numeric(10, 2), nullable=False, default=0)
        subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)

        __table_args__ = (
            db.CheckConstraint("cantidad > 0", name="ck_detalle_cantidad_pos"),
            db.CheckConstraint("precio_unitario >= 0", name="ck_detalle_pu_nonneg"),
            db.CheckConstraint("subtotal >= 0", name="ck_detalle_subtotal_nonneg"),
        )

        factura = db.relationship("Factura", back_populates="detalles")
        producto = db.relationship("Producto", back_populates="detalles")

        def calcular_subtotal(self):
            self.subtotal = (self.precio_unitario or Decimal("0")) * (self.cantidad or 0)

        def __repr__(self):
            return f"<Det {self.id} fac:{self.factura_id} prod:{self.producto_id} x{self.cantidad} = {self.subtotal}>"

    # =====================
    #       FORMULARIOS
    # =====================
    class ClienteForm(FlaskForm):
        nombre = StringField("Nombre", validators=[DataRequired(), Length(max=120)])
        direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
        telefono = StringField("Teléfono", validators=[Optional(), Length(max=50)])
        email = StringField("Email", validators=[Optional(), Email(), Length(max=120)])
        submit = SubmitField("Guardar")

    class ProductoForm(FlaskForm):
        descripcion = StringField("Descripción", validators=[DataRequired(), Length(max=200)])
        precio = DecimalField(
            "Precio",
            places=2,
            rounding=None,
            validators=[DataRequired(), NumberRange(min=0.01, message="Debe ser > 0")],
        )
        stock = IntegerField("Stock", validators=[DataRequired(), NumberRange(min=0, message="Debe ser ≥ 0")])
        submit = SubmitField("Guardar")

    # =====================
    #         RUTAS
    # =====================
    @app.route("/")
    @login_required
    def index():
        return render_template("index.html", user=current_user)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            u = User.query.filter_by(email=email).first()
            if u and u.check_password(password):
                login_user(u)
                return redirect(url_for("index"))
            flash("Credenciales inválidas", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # ----- CLIENTES: listado / alta / edición / eliminación -----
    @app.route("/clientes")
    @login_required
    @roles_required('admin')
    def clientes_list():
        clientes = Cliente.query.order_by(Cliente.id.desc()).all()
        return render_template("clientes/list.html", clientes=clientes)

    @app.route("/clientes/nuevo", methods=["GET", "POST"])
    @login_required
    @roles_required('admin')
    def clientes_nuevo():
        form = ClienteForm()
        if form.validate_on_submit():
            c = Cliente(
                nombre=form.nombre.data.strip(),
                direccion=(form.direccion.data or "").strip() or None,
                telefono=(form.telefono.data or "").strip() or None,
                email=(form.email.data or "").strip().lower() or None,
            )
            db.session.add(c)
            db.session.commit()
            flash("Cliente creado correctamente.", "success")
            return redirect(url_for("clientes_list"))
        return render_template("clientes/form.html", form=form, modo="nuevo")

    @app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
    @login_required
    @roles_required('admin')
    def clientes_editar(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        form = ClienteForm(obj=cliente)
        if form.validate_on_submit():
            cliente.nombre = form.nombre.data.strip()
            cliente.direccion = (form.direccion.data or "").strip() or None
            cliente.telefono = (form.telefono.data or "").strip() or None
            cliente.email = (form.email.data or "").strip().lower() or None
            db.session.commit()
            flash("Cliente actualizado.", "success")
            return redirect(url_for("clientes_list"))
        return render_template("clientes/form.html", form=form, modo="editar", cliente=cliente)

    @app.route("/clientes/<int:cliente_id>/eliminar", methods=["POST"])
    @login_required
    @roles_required('admin')
    def clientes_eliminar(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        if cliente.facturas.count() > 0:
            flash("No se puede eliminar: el cliente tiene facturas asociadas.", "warning")
            return redirect(url_for("clientes_list"))
        db.session.delete(cliente)
        db.session.commit()
        flash("Cliente eliminado.", "success")
        return redirect(url_for("clientes_list"))

    # ----- FACTURAS: alta con detalle y actualización de stock -----
    @app.route("/facturas/nueva", methods=["GET", "POST"])
    @login_required
    def facturas_nueva():
        clientes = Cliente.query.order_by(Cliente.nombre.asc()).all()
        productos = Producto.query.order_by(Producto.descripcion.asc()).all()

        ROWS = 5
        prev = {"cliente_id": request.form.get("cliente_id", type=int)}
        for i in range(1, ROWS + 1):
            prev[f"product_id_{i}"] = request.form.get(f"product_id_{i}", type=int)
            prev[f"cantidad_{i}"] = request.form.get(f"cantidad_{i}", type=int)

        if request.method == "POST":
            cliente_id = request.form.get("cliente_id", type=int)
            if not cliente_id:
                flash("Selecciona un cliente.", "warning")
                return render_template("facturas/nueva.html", clientes=clientes, productos=productos, rows=ROWS, prev=prev)

            items = []
            for i in range(1, ROWS + 1):
                pid = request.form.get(f"product_id_{i}", type=int)
                qty = request.form.get(f"cantidad_{i}", type=int)
                if pid and qty:
                    if qty <= 0:
                        flash("La cantidad debe ser mayor que 0.", "warning")
                        return render_template("facturas/nueva.html", clientes=clientes, productos=productos, rows=ROWS, prev=prev)
                    items.append((pid, qty))

            if not items:
                flash("Agrega al menos un producto.", "warning")
                return render_template("facturas/nueva.html", clientes=clientes, productos=productos, rows=ROWS, prev=prev)

            agg = {}
            for pid, qty in items:
                agg[pid] = agg.get(pid, 0) + qty

            prods = Producto.query.filter(Producto.id.in_(list(agg.keys()))).all()
            by_id = {p.id: p for p in prods}
            faltan = [pid for pid in agg if pid not in by_id]
            if faltan:
                flash("Producto inexistente en la selección.", "warning")
                return render_template("facturas/nueva.html", clientes=clientes, productos=productos, rows=ROWS, prev=prev)

            insuf = []
            for pid, qty in agg.items():
                p = by_id[pid]
                stock = p.stock or 0
                if qty > stock:
                    insuf.append(f"{p.descripcion} (stock {stock}, pedido {qty})")
            if insuf:
                flash("Stock insuficiente para: " + ", ".join(insuf), "warning")
                return render_template("facturas/nueva.html", clientes=clientes, productos=productos, rows=ROWS, prev=prev)

            factura = Factura(cliente_id=cliente_id, fecha=datetime.utcnow(), total=Decimal("0"))
            db.session.add(factura)

            for pid, qty in agg.items():
                p = by_id[pid]
                precio = p.precio or Decimal("0")
                det = DetalleFactura(
                    factura=factura,
                    producto=p,
                    cantidad=qty,
                    precio_unitario=precio
                )
                det.calcular_subtotal()
                db.session.add(det)
                p.stock = (p.stock or 0) - qty

            factura.recalcular_total()
            db.session.commit()
            flash("Factura creada correctamente.", "success")
            return redirect(url_for("facturas_detalle", factura_id=factura.id))

        return render_template("facturas/nueva.html", clientes=clientes, productos=productos, rows=ROWS, prev=prev)

    @app.route("/facturas/<int:factura_id>")
    @login_required
    def facturas_detalle(factura_id):
        f = Factura.query.get_or_404(factura_id)
        return render_template("facturas/detalle.html", f=f)

    # ----- PRODUCTOS: listado / alta / edición / eliminación -----
    @app.route("/productos")
    @login_required
    @roles_required('admin')
    def productos_list():
        productos = Producto.query.order_by(Producto.id.desc()).all()
        return render_template("productos/list.html", productos=productos)

    @app.route("/productos/nuevo", methods=["GET", "POST"])
    @login_required
    @roles_required('admin')
    def productos_nuevo():
        form = ProductoForm()
        if form.validate_on_submit():
            p = Producto(
                descripcion=form.descripcion.data.strip(),
                precio=form.precio.data,
                stock=form.stock.data
            )
            db.session.add(p)
            db.session.commit()
            flash("Producto creado correctamente.", "success")
            return redirect(url_for("productos_list"))
        return render_template("productos/form.html", form=form, modo="nuevo")

    @app.route("/productos/<int:producto_id>/editar", methods=["GET", "POST"])
    @login_required
    @roles_required('admin')
    def productos_editar(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        form = ProductoForm(obj=producto)
        if form.validate_on_submit():
            producto.descripcion = form.descripcion.data.strip()
            producto.precio = form.precio.data
            producto.stock = form.stock.data
            db.session.commit()
            flash("Producto actualizado.", "success")
            return redirect(url_for("productos_list"))
        return render_template("productos/form.html", form=form, modo="editar", producto=producto)

    @app.route("/productos/<int:producto_id>/eliminar", methods=["POST"])
    @login_required
    @roles_required('admin')
    def productos_eliminar(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        if producto.detalles and len(producto.detalles) > 0:
            flash("No se puede eliminar: el producto está usado en facturas.", "warning")
            return redirect(url_for("productos_list"))
        db.session.delete(producto)
        db.session.commit()
        flash("Producto eliminado.", "success")
        return redirect(url_for("productos_list"))

    # ----- LISTADO DE FACTURAS con filtros -----
    def _parse_date_yyyy_mm_dd(s: str):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None

    @app.route("/facturas")
    @login_required
    def facturas_list():
        cliente_id = request.args.get("cliente_id", type=int)
        desde_str = request.args.get("desde", type=str)
        hasta_str = request.args.get("hasta", type=str)

        desde_dt = _parse_date_yyyy_mm_dd(desde_str)
        hasta_dt = _parse_date_yyyy_mm_dd(hasta_str)

        q = Factura.query
        if cliente_id:
            q = q.filter(Factura.cliente_id == cliente_id)
        if desde_dt:
            q = q.filter(Factura.fecha >= desde_dt)
        if hasta_dt:
            fin_dia = hasta_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            q = q.filter(Factura.fecha <= fin_dia)

        facturas = q.order_by(Factura.fecha.desc(), Factura.id.desc()).all()
        clientes = Cliente.query.order_by(Cliente.nombre.asc()).all()

        filtros = {
            "cliente_id": cliente_id,
            "desde": desde_str or "",
            "hasta": hasta_str or "",
        }
        return render_template("facturas/list.html", facturas=facturas, clientes=clientes, filtros=filtros)

    # ----- REPORTES -----
    @app.route("/reportes/ventas")
    @login_required
    @roles_required('admin')
    def reportes_ventas():
        desde_str = request.args.get("desde", type=str)
        hasta_str = request.args.get("hasta", type=str)
        desde_dt = _parse_date_yyyy_mm_dd(desde_str)
        hasta_dt = _parse_date_yyyy_mm_dd(hasta_str)

        q = Factura.query
        if desde_dt:
            q = q.filter(Factura.fecha >= desde_dt)
        if hasta_dt:
            fin_dia = hasta_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            q = q.filter(Factura.fecha <= fin_dia)

        facturas = q.order_by(Factura.fecha.desc(), Factura.id.desc()).all()
        total = sum((f.total or Decimal("0")) for f in facturas)
        conteo = len(facturas)
        filtros = {"desde": desde_str or "", "hasta": hasta_str or ""}
        return render_template("reportes/ventas.html", facturas=facturas, total=total, conteo=conteo, filtros=filtros)

    @app.route("/reportes/facturas-por-cliente")
    @login_required
    @roles_required('admin')
    def reportes_facturas_por_cliente():
        cliente_id = request.args.get("cliente_id", type=int)
        desde_str = request.args.get("desde", type=str)
        hasta_str = request.args.get("hasta", type=str)

        desde_dt = _parse_date_yyyy_mm_dd(desde_str)
        hasta_dt = _parse_date_yyyy_mm_dd(hasta_str)

        clientes = Cliente.query.order_by(Cliente.nombre.asc()).all()
        facturas = []
        total = Decimal("0")
        if cliente_id:
            q = Factura.query.filter(Factura.cliente_id == cliente_id)
            if desde_dt:
                q = q.filter(Factura.fecha >= desde_dt)
            if hasta_dt:
                fin_dia = hasta_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                q = q.filter(Factura.fecha <= fin_dia)
            facturas = q.order_by(Factura.fecha.desc(), Factura.id.desc()).all()
            total = sum((f.total or Decimal("0")) for f in facturas)

        filtros = {"cliente_id": cliente_id, "desde": desde_str or "", "hasta": hasta_str or ""}
        return render_template("reportes/facturas_clientes.html", clientes=clientes, facturas=facturas, total=total, filtros=filtros)

    @app.route("/debug/conteos")
    @login_required
    @roles_required('admin')
    def debug_conteos():
        clientes = Cliente.query.count()
        productos = Producto.query.count()
        facturas = Factura.query.count()
        detalles = DetalleFactura.query.count()
        return (
            f"OK | clientes={clientes}, productos={productos}, "
            f"facturas={facturas}, detalles={detalles}"
        )

    # =====================
    #     INIT DB + SEED
    # =====================
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(email="administrador@facturas.com").first():
            admin = User(email="administrador@facturas.com", role="admin")
            admin.set_password("admin")
            db.session.add(admin)
        if not User.query.filter_by(email="usuario@facturas.com").first():
            user = User(email="usuario@facturas.com", role="user")
            user.set_password("user")
            db.session.add(user)

        if not Cliente.query.first():
            db.session.add(Cliente(nombre="Cliente demo", email="cliente@demo.com"))
        if not Producto.query.first():
            db.session.add(Producto(descripcion="Producto demo", precio=Decimal("100.00"), stock=10))

        db.session.commit()

    return app


# Comandos utilitarios desde CLI:
# - python app.py resetdb   -> Borra datos de todas las tablas (excepto usuarios)
# - python app.py run       -> Ejecuta el servidor de desarrollo
if __name__ == "__main__":
    app = create_app()

    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "resetdb":
        with app.app_context():
            # Borrar datos excepto usuarios
            from sqlalchemy import text
            db.session.execute(text("DELETE FROM detalle_factura"))
            db.session.execute(text("DELETE FROM facturas"))
            db.session.execute(text("DELETE FROM productos"))
            db.session.execute(text("DELETE FROM clientes"))
            db.session.commit()
            print("Base reiniciada (se conservaron usuarios).")
    else:
        print("Flask en http://127.0.0.1:5000  |  Usuarios demo: administrador@facturas.com/admin  ·  usuario@facturas.com/user")
        app.run(debug=True)
