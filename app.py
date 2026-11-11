import os, sqlite3, smtplib
from email.message import EmailMessage
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "CAMBIAR-ESTA-CLAVE-ANTES-DE-USAR")
DB = os.getenv("DATABASE_PATH", "servilujos.db")
COP = Decimal("0.01")

def money(value):
    return Decimal(str(value)).quantize(COP, rounding=ROUND_HALF_UP)

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clients(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, document TEXT, email TEXT, phone TEXT,
            address TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT, price TEXT NOT NULL,
            tax_rate TEXT NOT NULL DEFAULT '0', stock INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY, number TEXT UNIQUE NOT NULL, client_id INTEGER,
            customer_name TEXT NOT NULL, customer_document TEXT, customer_email TEXT,
            created_at TEXT NOT NULL, subtotal TEXT NOT NULL, tax_total TEXT NOT NULL,
            total TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'BORRADOR',
            notes TEXT, FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS sale_items(
            id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, product_id INTEGER,
            description TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price TEXT NOT NULL,
            tax_rate TEXT NOT NULL, line_subtotal TEXT NOT NULL, line_tax TEXT NOT NULL,
            line_total TEXT NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        if not con.execute("SELECT id FROM users LIMIT 1").fetchone():
            username = os.getenv("ADMIN_USER", "admin")
            password = os.getenv("ADMIN_PASSWORD", "Cambiar123!")
            con.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                        (username, generate_password_hash(password)))
        defaults = {
            "business_name": "SERVILUJOS LA PRIMERA",
            "business_address": "Av. 1 #19B-28, Bogotá, Colombia",
            "business_phone": "",
            "business_email": "",
            "business_nit": "",
            "legal_notice": "COMPROBANTE INTERNO - NO ES FACTURA ELECTRÓNICA VALIDADA POR LA DIAN"
        }
        for k, v in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k,v))

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def setting_map():
    with db() as con:
        return {r["key"]: r["value"] for r in con.execute("SELECT * FROM settings")}

@app.template_filter("cop")
def cop(value):
    try:
        return f"${Decimal(str(value)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "$0,00"

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (request.form.get("username",""),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password","")):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/")
@login_required
def dashboard():
    with db() as con:
        sales = con.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 8").fetchall()
        totals = con.execute("SELECT COUNT(*) n, COALESCE(SUM(CAST(total AS REAL)),0) total FROM sales").fetchone()
        clients = con.execute("SELECT COUNT(*) n FROM clients").fetchone()["n"]
        products = con.execute("SELECT COUNT(*) n FROM products WHERE active=1").fetchone()["n"]
    return render_template("dashboard.html", sales=sales, totals=totals, clients=clients, products=products)

@app.route("/clientes", methods=["GET","POST"])
@login_required
def clients():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if not name:
            flash("El nombre del cliente es obligatorio.", "error")
        else:
            with db() as con:
                con.execute("""INSERT INTO clients(name,document,email,phone,address,created_at)
                VALUES(?,?,?,?,?,?)""", (name, request.form.get("document","").strip(),
                request.form.get("email","").strip(), request.form.get("phone","").strip(),
                request.form.get("address","").strip(), datetime.now().isoformat(timespec="minutes")))
            flash("Cliente guardado.", "success")
        return redirect(url_for("clients"))
    with db() as con:
        rows = con.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return render_template("clients.html", rows=rows)

@app.route("/clientes/<int:client_id>/editar", methods=["GET","POST"])
@login_required
def edit_client(client_id):
    with db() as con:
        row = con.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        if not row: abort(404)
        if request.method == "POST":
            name=request.form.get("name","").strip()
            if not name:
                flash("El nombre es obligatorio.", "error")
            else:
                con.execute("""UPDATE clients SET name=?,document=?,email=?,phone=?,address=? WHERE id=?""",
                    (name,request.form.get("document",""),request.form.get("email",""),
                     request.form.get("phone",""),request.form.get("address",""),client_id))
                flash("Cliente actualizado.", "success")
                return redirect(url_for("clients"))
    return render_template("edit_client.html", row=row)

@app.route("/productos", methods=["GET","POST"])
@login_required
def products():
    if request.method == "POST":
        name=request.form.get("name","").strip()
        try:
            price=money(request.form.get("price","0"))
            tax=Decimal(request.form.get("tax_rate","0"))
            stock=int(request.form.get("stock","0"))
            if not name or price < 0 or tax < 0 or tax > 100 or stock < 0: raise ValueError()
        except Exception:
            flash("Revisa nombre, precio, IVA (0 a 100) e inventario.", "error")
            return redirect(url_for("products"))
        with db() as con:
            con.execute("INSERT INTO products(name,code,price,tax_rate,stock) VALUES(?,?,?,?,?)",
                        (name,request.form.get("code","").strip(),str(price),str(tax),stock))
        flash("Producto guardado.", "success")
        return redirect(url_for("products"))
    with db() as con:
        rows=con.execute("SELECT * FROM products WHERE active=1 ORDER BY name").fetchall()
    return render_template("products.html", rows=rows)

@app.post("/productos/<int:product_id>/desactivar")
@login_required
def deactivate_product(product_id):
    with db() as con:
        con.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))
    flash("Producto desactivado.", "success")
    return redirect(url_for("products"))

@app.route("/ventas/nueva", methods=["GET","POST"])
@login_required
def new_sale():
    with db() as con:
        clients=con.execute("SELECT * FROM clients ORDER BY name").fetchall()
        products=con.execute("SELECT * FROM products WHERE active=1 ORDER BY name").fetchall()
    if request.method == "POST":
        client_id=request.form.get("client_id") or None
        customer_name=request.form.get("customer_name","").strip()
        customer_doc=request.form.get("customer_document","").strip()
        customer_email=request.form.get("customer_email","").strip()
        ids=request.form.getlist("product_id[]")
        qtys=request.form.getlist("quantity[]")
        if client_id:
            with db() as con:
                client=con.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            if client:
                customer_name=client["name"]; customer_doc=client["document"] or ""
                customer_email=client["email"] or ""
        if not customer_name or not ids:
            flash("Selecciona un cliente o escribe su nombre y agrega al menos un producto.", "error")
            return redirect(url_for("new_sale"))
        items=[]; subtotal=Decimal("0"); tax_total=Decimal("0")
        try:
            with db() as con:
                for pid, q in zip(ids, qtys):
                    product=con.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
                    quantity=int(q)
                    if not product or quantity < 1: raise ValueError()
                    unit=Decimal(product["price"]); rate=Decimal(product["tax_rate"])
                    line_sub=money(unit*quantity); line_tax=money(line_sub*rate/Decimal("100"))
                    line_total=line_sub+line_tax
                    items.append((int(pid),product["name"],quantity,str(unit),str(rate),str(line_sub),str(line_tax),str(line_total)))
                    subtotal+=line_sub; tax_total+=line_tax
                total=subtotal+tax_total
                number=f"SLP-{datetime.now():%Y%m%d-%H%M%S}"
                cur=con.execute("""INSERT INTO sales(number,client_id,customer_name,customer_document,customer_email,
                    created_at,subtotal,tax_total,total,status,notes) VALUES(?,?,?,?,?,?,?,?,?,'BORRADOR',?)""",
                    (number,client_id,customer_name,customer_doc,customer_email,
                     datetime.now().isoformat(timespec="seconds"),str(subtotal),str(tax_total),str(total),
                     request.form.get("notes","").strip()))
                sale_id=cur.lastrowid
                for item in items:
                    con.execute("""INSERT INTO sale_items(sale_id,product_id,description,quantity,unit_price,
                    tax_rate,line_subtotal,line_tax,line_total) VALUES(?,?,?,?,?,?,?,?,?)""", (sale_id,*item))
            flash("Venta guardada. Puedes consultar o imprimir el comprobante.", "success")
            return redirect(url_for("sale_detail", sale_id=sale_id))
        except Exception:
            flash("No se pudo guardar. Verifica los productos y las cantidades.", "error")
            return redirect(url_for("new_sale"))
    return render_template("new_sale.html", clients=clients, products=products)

@app.get("/ventas/<int:sale_id>")
@login_required
def sale_detail(sale_id):
    with db() as con:
        sale=con.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale: abort(404)
        items=con.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
    return render_template("sale_detail.html", sale=sale, items=items)

def make_pdf(sale, items, settings):
    buf=BytesIO(); p=canvas.Canvas(buf, pagesize=letter)
    width,height=letter; y=height-55
    p.setFont("Helvetica-Bold", 18); p.drawString(45,y,settings.get("business_name","SERVILUJOS LA PRIMERA")); y-=24
    p.setFont("Helvetica",9)
    for line in [settings.get("business_address",""), "Tel: "+settings.get("business_phone",""), "NIT/CC: "+settings.get("business_nit","")]:
        if line.strip(): p.drawString(45,y,line); y-=14
    y-=10; p.setFont("Helvetica-Bold",13); p.drawString(45,y,"COMPROBANTE INTERNO DE VENTA"); y-=20
    p.setFont("Helvetica",9)
    p.drawString(45,y,f"Consecutivo: {sale['number']}"); p.drawString(360,y,f"Fecha: {sale['created_at'][:16]}"); y-=16
    p.drawString(45,y,f"Cliente: {sale['customer_name']}"); y-=14
    p.drawString(45,y,f"Documento: {sale['customer_document'] or 'No registrado'}"); y-=14
    p.drawString(45,y,f"Correo: {sale['customer_email'] or 'No registrado'}"); y-=25
    p.setFont("Helvetica-Bold",9)
    p.drawString(45,y,"Producto"); p.drawString(300,y,"Cant."); p.drawString(350,y,"Precio"); p.drawString(435,y,"IVA"); p.drawString(500,y,"Total")
    y-=8; p.line(45,y,565,y); y-=16; p.setFont("Helvetica",8)
    for it in items:
        if y < 100: p.showPage(); y=height-55
        p.drawString(45,y,str(it["description"])[:42]); p.drawRightString(330,y,str(it["quantity"]))
        p.drawRightString(410,y,f"${Decimal(it['unit_price']):,.2f}")
        p.drawRightString(475,y,f"{it['tax_rate']}%")
        p.drawRightString(565,y,f"${Decimal(it['line_total']):,.2f}")
        y-=17
    y-=10; p.line(350,y,565,y); y-=20; p.setFont("Helvetica",10)
    p.drawRightString(565,y,f"Subtotal: ${Decimal(sale['subtotal']):,.2f}"); y-=16
    p.drawRightString(565,y,f"Impuestos: ${Decimal(sale['tax_total']):,.2f}"); y-=18
    p.setFont("Helvetica-Bold",12); p.drawRightString(565,y,f"TOTAL: ${Decimal(sale['total']):,.2f}")
    y-=35; p.setFont("Helvetica-Bold",8); p.drawString(45,y,settings.get("legal_notice","COMPROBANTE INTERNO - NO ES FACTURA ELECTRÓNICA"))
    p.save(); buf.seek(0); return buf

@app.get("/ventas/<int:sale_id>/pdf")
@login_required
def sale_pdf(sale_id):
    with db() as con:
        sale=con.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        items=con.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
    if not sale: abort(404)
    pdf=make_pdf(sale,items,setting_map())
    return send_file(pdf, as_attachment=True, download_name=f"{sale['number']}.pdf", mimetype="application/pdf")

@app.post("/ventas/<int:sale_id>/enviar")
@login_required
def send_sale_email(sale_id):
    with db() as con:
        sale=con.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        items=con.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
    if not sale or not sale["customer_email"]:
        flash("El cliente no tiene un correo registrado.", "error")
        return redirect(url_for("sale_detail",sale_id=sale_id))
    host=os.getenv("SMTP_HOST"); user=os.getenv("SMTP_USER"); password=os.getenv("SMTP_PASSWORD")
    if not all([host,user,password,os.getenv("SMTP_FROM")]):
        flash("Configura SMTP_HOST, SMTP_USER, SMTP_PASSWORD y SMTP_FROM en el archivo .env.", "error")
        return redirect(url_for("sale_detail",sale_id=sale_id))
    try:
        msg=EmailMessage()
        msg["Subject"]=f"Comprobante de venta {sale['number']} - SERVILUJOS LA PRIMERA"
        msg["From"]=os.getenv("SMTP_FROM"); msg["To"]=sale["customer_email"]
        msg.set_content(f"Hola {sale['customer_name']},\n\nAdjuntamos el comprobante interno de tu compra.\nTotal: ${sale['total']} COP\n\nEste documento no es una factura electrónica validada por la DIAN.")
        pdf=make_pdf(sale,items,setting_map())
        msg.add_attachment(pdf.read(), maintype="application", subtype="pdf", filename=f"{sale['number']}.pdf")
        with smtplib.SMTP(host,int(os.getenv("SMTP_PORT","587"))) as server:
            server.starttls(); server.login(user,password); server.send_message(msg)
        flash("Comprobante enviado por correo.", "success")
    except Exception as exc:
        app.logger.exception("Error SMTP")
        flash("No se pudo enviar el correo. Revisa la configuración SMTP.", "error")
    return redirect(url_for("sale_detail",sale_id=sale_id))

@app.get("/ventas")
@login_required
def sales_list():
    with db() as con:
        rows=con.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
    return render_template("sales.html", rows=rows)

@app.route("/configuracion", methods=["GET","POST"])
@login_required
def settings():
    if request.method=="POST":
        values={k:request.form.get(k,"").strip() for k in
            ["business_name","business_address","business_phone","business_email","business_nit"]}
        with db() as con:
            for k,v in values.items():
                con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v))
        flash("Configuración guardada.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", settings=setting_map())

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"),404

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT","5000")), debug=os.getenv("FLASK_DEBUG","0")=="1")
