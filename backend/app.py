from __future__ import annotations

import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


PROJECT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_DIR / "frontend"
load_dotenv(Path(__file__).resolve().parent / ".env")
DATABASE_CONFIG = {
    "host": os.environ.get("PGHOST", "127.0.0.1"),
    "port": int(os.environ.get("PGPORT", "5432")),
    "dbname": os.environ.get("PGDATABASE", "transformacao_digital_mvp"),
    "sslmode": os.environ.get("PGSSLMODE", "prefer"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", ""),
}


class DatabaseConnection:
    """Small adapter that lets the app use familiar DB-API calls with psycopg."""

    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()

    @staticmethod
    def _query(statement: str) -> str:
        return statement.replace("?", "%s")

    def execute(self, statement: str, parameters: Any = None):
        return self.connection.execute(self._query(statement), parameters)

    def executemany(self, statement: str, parameters: Any):
        return self.connection.cursor().executemany(self._query(statement), parameters)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def connect_database(database: str | None = None, *, autocommit: bool = False) -> DatabaseConnection:
    settings = {**DATABASE_CONFIG, "row_factory": dict_row}
    if database:
        settings["dbname"] = database
    return DatabaseConnection(psycopg.connect(**settings, autocommit=autocommit))

app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR / "templates"),
    static_folder=str(FRONTEND_DIR / "static"),
)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-only-change-this-key"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

STATUSES = ("Aberto", "Em atendimento", "Aguardando informações", "Concluído")
CATEGORIES = ("Equipamento", "Rede", "Software", "Conta e acesso", "Outro")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")


def get_db() -> DatabaseConnection:
    if "db" not in g:
        g.db = connect_database()
    return g.db


@app.teardown_appcontext
def close_db(_error: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@app.get("/healthz")
def healthz():
    try:
        get_db().execute("SELECT 1")
    except psycopg.Error:
        app.logger.exception("Verificação de saúde não conseguiu acessar o PostgreSQL.")
        return jsonify(status="unavailable"), 503
    return jsonify(status="ok")

def init_db() -> None:
    # O banco informado em PGDATABASE já deve existir no serviço PostgreSQL.
    # A aplicação cria apenas as tabelas do MVP, sem exigir permissão CREATEDB.
    connection = connect_database()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student', 'technician')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id BIGSERIAL PRIMARY KEY,
            protocol TEXT UNIQUE,
            requester_id BIGINT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Aberto',
            assigned_to_id BIGINT REFERENCES users(id),
            estimated_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ticket_events (
            id BIGSERIAL PRIMARY KEY,
            ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            author_id BIGINT REFERENCES users(id),
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticket_id BIGINT REFERENCES tickets(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_requester ON tickets(requester_id);
        CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
        CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(ticket_id, id);
        CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read_at);
        """
    )

    if connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"] == 0:
        stamp = now_iso()
        connection.executemany(
            "INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
            [
                (
                    "Ana Souza",
                    "aluna@example.test",
                    "+55 11 90000-0001",
                    generate_password_hash("aluno123"),
                    "student",
                    stamp,
                ),
                (
                    "Cristiano Oliveira",
                    "cristiano@example.test",
                    "+55 11 90000-0003",
                    generate_password_hash("aluno123"),
                    "student",
                    stamp,
                ),
                (
                    "Marcos Lima",
                    "tecnico@example.test",
                    "+55 11 90000-0002",
                    generate_password_hash("tecnico123"),
                    "technician",
                    stamp,
                ),
            ],
        )
        student_id = connection.execute(
            "SELECT id FROM users WHERE role='student'"
        ).fetchone()["id"]
        tech_id = connection.execute(
            "SELECT id FROM users WHERE role='technician'"
        ).fetchone()["id"]
        examples = [
            (
                "Projetor sem imagem",
                "Equipamento",
                "Laboratório de exemplo 1",
                "O projetor liga, mas não exibe a imagem do computador.",
                "Em atendimento",
                tech_id,
                (datetime.now().astimezone() + timedelta(days=1)).isoformat(timespec="minutes"),
            ),
            (
                "Acesso à estação",
                "Conta e acesso",
                "Laboratório de exemplo 2",
                "Não consigo entrar na estação usando minha conta de demonstração.",
                "Aguardando informações",
                tech_id,
                None,
            ),
            (
                "Teclado com falha",
                "Equipamento",
                "Laboratório de exemplo 1",
                "Algumas teclas não respondem durante a digitação.",
                "Concluído",
                tech_id,
                None,
            ),
        ]
        for title, category, location, description, status, assigned, estimate in examples:
            created = now_iso()
            cursor = connection.execute(
                """INSERT INTO tickets
                (requester_id,title,category,location,description,status,assigned_to_id,
                 estimated_at,created_at,updated_at,closed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                (
                    student_id,
                    title,
                    category,
                    location,
                    description,
                    status,
                    assigned,
                    estimate,
                    created,
                    created,
                    created if status == "Concluído" else None,
                ),
            )
            ticket_id = cursor.fetchone()["id"]
            protocol = f"LAB-{datetime.now().year}-{ticket_id:04d}"
            connection.execute(
                "UPDATE tickets SET protocol=? WHERE id=?", (protocol, ticket_id)
            )
            connection.execute(
                """INSERT INTO ticket_events
                (ticket_id,author_id,event_type,from_status,to_status,message,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    student_id,
                    "opened",
                    None,
                    "Aberto",
                    "Chamado criado no conjunto de dados fictícios da demonstração.",
                    created,
                ),
            )
            if status != "Aberto":
                message = (
                    "A equipe técnica iniciou o atendimento."
                    if status == "Em atendimento"
                    else "A equipe solicitou um complemento para seguir com o atendimento."
                    if status == "Aguardando informações"
                    else "Atendimento concluído no exemplo de demonstração."
                )
                connection.execute(
                    """INSERT INTO ticket_events
                    (ticket_id,author_id,event_type,from_status,to_status,message,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (ticket_id, tech_id, "status", "Aberto", status, message, created),
                )
        connection.commit()
    connection.close()


def user_by_id(user_id: int | None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


@app.before_request
def load_current_user() -> None:
    g.user = user_by_id(session.get("user_id"))


@app.context_processor
def template_globals() -> dict[str, Any]:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return {"current_user": getattr(g, "user", None), "csrf_token": session["csrf_token"]}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Sua sessão terminou. Entre novamente."), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def technician_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "technician":
            if request.path.startswith("/api/"):
                return jsonify(error="Esta ação é exclusiva da equipe técnica."), 403
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def csrf_required() -> None:
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        abort(400, description="Token de segurança ausente ou inválido.")


def json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def clean_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def add_event(
    connection: DatabaseConnection,
    ticket_id: int,
    author_id: int | None,
    event_type: str,
    message: str,
    from_status: str | None = None,
    to_status: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO ticket_events
        (ticket_id,author_id,event_type,from_status,to_status,message,created_at)
        VALUES(?,?,?,?,?,?,?)""",
        (ticket_id, author_id, event_type, from_status, to_status, message, now_iso()),
    )


def send_optional_email(recipient: dict[str, Any], title: str, message: str) -> None:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host or not recipient["email"]:
        return
    try:
        mail = EmailMessage()
        mail["Subject"] = f"[Ocorrências do laboratório] {title}"
        mail["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USERNAME", "")
        mail["To"] = recipient["email"]
        mail.set_content(f"Olá, {recipient['name']}.\n\n{message}\n")
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=5) as server:
            if os.environ.get("SMTP_USE_TLS", "true").lower() == "true":
                server.starttls()
            username = os.environ.get("SMTP_USERNAME", "")
            password = os.environ.get("SMTP_PASSWORD", "")
            if username:
                server.login(username, password)
            server.send_message(mail)
    except (OSError, smtplib.SMTPException, ValueError) as error:
        app.logger.warning("Aviso por e-mail não enviado: %s", error)


def notify_user(
    connection: DatabaseConnection,
    user_id: int,
    ticket_id: int,
    title: str,
    message: str,
) -> None:
    connection.execute(
        """INSERT INTO notifications(user_id,ticket_id,title,message,created_at)
        VALUES(?,?,?,?,?)""",
        (user_id, ticket_id, title, message, now_iso()),
    )
    recipient = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if recipient:
        send_optional_email(recipient, title, message)


def get_ticket(ticket_id: int) -> dict[str, Any]:
    ticket = get_db().execute(
        """SELECT t.*, requester.name AS requester_name,
                  assigned.name AS assigned_name
           FROM tickets t
           JOIN users requester ON requester.id=t.requester_id
           LEFT JOIN users assigned ON assigned.id=t.assigned_to_id
           WHERE t.id=?""",
        (ticket_id,),
    ).fetchone()
    if ticket is None:
        abort(404)
    if g.user["role"] != "technician" and ticket["requester_id"] != g.user["id"]:
        abort(404)
    return ticket


def ticket_json(ticket: dict[str, Any]) -> dict[str, Any]:
    events = get_db().execute(
        """SELECT e.*, u.name AS author_name, u.role AS author_role
           FROM ticket_events e LEFT JOIN users u ON u.id=e.author_id
           WHERE e.ticket_id=? ORDER BY e.id""",
        (ticket["id"],),
    ).fetchall()
    return {
        "id": ticket["id"],
        "protocol": ticket["protocol"],
        "requester_id": ticket["requester_id"],
        "requester_name": ticket["requester_name"],
        "title": ticket["title"],
        "category": ticket["category"],
        "location": ticket["location"],
        "description": ticket["description"],
        "status": ticket["status"],
        "assigned_to_id": ticket["assigned_to_id"],
        "assigned_name": ticket["assigned_name"],
        "estimated_at": ticket["estimated_at"],
        "created_at": ticket["created_at"],
        "updated_at": ticket["updated_at"],
        "closed_at": ticket["closed_at"],
        "events": [dict(event) for event in events],
    }


def ticket_rows_for_user() -> list[dict[str, Any]]:
    if g.user["role"] == "technician":
        return get_db().execute(
            """SELECT t.*, requester.name AS requester_name,
                      assigned.name AS assigned_name
               FROM tickets t JOIN users requester ON requester.id=t.requester_id
               LEFT JOIN users assigned ON assigned.id=t.assigned_to_id
               ORDER BY CASE t.status WHEN 'Aberto' THEN 0
                    WHEN 'Aguardando informações' THEN 1
                    WHEN 'Em atendimento' THEN 2 ELSE 3 END, t.updated_at DESC"""
        ).fetchall()
    return get_db().execute(
        """SELECT t.*, requester.name AS requester_name,
                  assigned.name AS assigned_name
           FROM tickets t JOIN users requester ON requester.id=t.requester_id
           LEFT JOIN users assigned ON assigned.id=t.assigned_to_id
           WHERE t.requester_id=? ORDER BY t.updated_at DESC""",
        (g.user["id"],),
    ).fetchall()


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("home"))
    if request.method == "POST":
        csrf_required()
        email = clean_text(request.form.get("email"), 180).lower()
        password = str(request.form.get("password") or "")
        user = get_db().execute(
            "SELECT * FROM users WHERE lower(email)=?", (email,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(24)
            next_path = request.args.get("next", "")
            if next_path.startswith("/") and not next_path.startswith("//"):
                return redirect(next_path)
            return redirect(url_for("home"))
        flash("E-mail ou senha não conferem.", "danger")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    csrf_required()
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def home():
    if g.user["role"] == "technician":
        return redirect(url_for("technician_dashboard"))
    return redirect(url_for("student_dashboard"))


@app.get("/painel")
@login_required
def student_dashboard():
    if g.user["role"] != "student":
        return redirect(url_for("technician_dashboard"))
    return render_template("dashboard.html", page="dashboard")


@app.get("/tecnico")
@technician_required
def technician_dashboard():
    return render_template("technician.html", page="technician")


@app.get("/chamados/novo")
@login_required
def new_ticket_page():
    if g.user["role"] != "student":
        abort(403)
    return render_template("new_ticket.html", page="new-ticket")


@app.get("/chamados/<int:ticket_id>")
@login_required
def ticket_page(ticket_id: int):
    ticket = get_ticket(ticket_id)
    return render_template("ticket_detail.html", page="ticket-detail", ticket=ticket)


@app.get("/perfil")
@login_required
def profile_page():
    return render_template("profile.html", page="profile")


@app.get("/api/me")
@login_required
def api_me():
    return jsonify(
        id=g.user["id"],
        name=g.user["name"],
        email=g.user["email"],
        phone=g.user["phone"],
        role=g.user["role"],
        role_label="Aluno" if g.user["role"] == "student" else "Equipe técnica",
    )


@app.get("/api/tickets")
@login_required
def api_tickets():
    tickets = ticket_rows_for_user()
    status = request.args.get("status")
    if status in STATUSES:
        tickets = [ticket for ticket in tickets if ticket["status"] == status]
    return jsonify([ticket_json(ticket) for ticket in tickets])


@app.post("/api/tickets")
@login_required
def api_create_ticket():
    if g.user["role"] != "student":
        return jsonify(error="A abertura de chamados está disponível para alunos."), 403
    csrf_required()
    data = json_body()
    title = clean_text(data.get("title"), 100)
    category = clean_text(data.get("category"), 50)
    location = clean_text(data.get("location"), 100)
    description = clean_text(data.get("description"), 1500)
    if not all((title, category, location, description)):
        return jsonify(error="Preencha os campos obrigatórios."), 400
    if category not in CATEGORIES:
        return jsonify(error="Selecione uma categoria válida."), 400
    if not (g.user["email"] or g.user["phone"]):
        return jsonify(error="Cadastre um e-mail ou telefone antes de abrir chamados."), 400

    connection = get_db()
    created = now_iso()
    cursor = connection.execute(
        """INSERT INTO tickets
        (requester_id,title,category,location,description,status,created_at,updated_at)
        VALUES(?,?,?,?,?,'Aberto',?,?) RETURNING id""",
        (g.user["id"], title, category, location, description, created, created),
    )
    ticket_id = cursor.fetchone()["id"]
    protocol = f"LAB-{datetime.now().year}-{ticket_id:04d}"
    connection.execute("UPDATE tickets SET protocol=? WHERE id=?", (protocol, ticket_id))
    add_event(
        connection,
        ticket_id,
        g.user["id"],
        "opened",
        "Chamado registrado. A equipe técnica poderá atualizar o andamento por aqui.",
        None,
        "Aberto",
    )
    notify_user(
        connection,
        g.user["id"],
        ticket_id,
        "Chamado registrado",
        f"O chamado {protocol} foi registrado e está aberto.",
    )
    connection.commit()
    return jsonify(id=ticket_id, protocol=protocol), 201


@app.get("/api/tickets/<int:ticket_id>")
@login_required
def api_ticket_detail(ticket_id: int):
    return jsonify(ticket_json(get_ticket(ticket_id)))


@app.post("/api/tickets/<int:ticket_id>/request-info")
@technician_required
def api_request_info(ticket_id: int):
    csrf_required()
    ticket = get_ticket(ticket_id)
    question = clean_text(json_body().get("message"), 1000)
    if not question:
        return jsonify(error="Escreva a informação necessária."), 400
    connection = get_db()
    before = ticket["status"]
    connection.execute(
        """UPDATE tickets SET status='Aguardando informações',assigned_to_id=?,updated_at=?
           WHERE id=?""",
        (g.user["id"], now_iso(), ticket_id),
    )
    add_event(
        connection,
        ticket_id,
        g.user["id"],
        "request_info",
        question,
        before,
        "Aguardando informações",
    )
    notify_user(
        connection,
        ticket["requester_id"],
        ticket_id,
        "Precisamos de mais informações",
        f"No chamado {ticket['protocol']}: {question}",
    )
    connection.commit()
    return jsonify(ok=True)


@app.post("/api/tickets/<int:ticket_id>/reply")
@login_required
def api_reply(ticket_id: int):
    csrf_required()
    ticket = get_ticket(ticket_id)
    if g.user["role"] != "student" or ticket["requester_id"] != g.user["id"]:
        return jsonify(error="Somente o solicitante pode responder aqui."), 403
    if ticket["status"] != "Aguardando informações":
        return jsonify(error="Este chamado não está aguardando complemento."), 409
    message = clean_text(json_body().get("message"), 1000)
    if not message:
        return jsonify(error="Escreva uma resposta para a equipe técnica."), 400
    connection = get_db()
    connection.execute(
        """UPDATE tickets SET status='Em atendimento',updated_at=? WHERE id=?""",
        (now_iso(), ticket_id),
    )
    add_event(
        connection,
        ticket_id,
        g.user["id"],
        "reply",
        message,
        "Aguardando informações",
        "Em atendimento",
    )
    technicians = connection.execute(
        "SELECT id FROM users WHERE role='technician'"
    ).fetchall()
    for technician in technicians:
        notify_user(
            connection,
            technician["id"],
            ticket_id,
            "Aluno respondeu ao chamado",
            f"Há uma nova resposta no chamado {ticket['protocol']}.",
        )
    connection.commit()
    return jsonify(ok=True)


@app.post("/api/tickets/<int:ticket_id>/actions")
@technician_required
def api_ticket_action(ticket_id: int):
    csrf_required()
    ticket = get_ticket(ticket_id)
    data = json_body()
    action = clean_text(data.get("action"), 30)
    connection = get_db()
    before = ticket["status"]
    assigned_to = g.user["id"]
    if action == "start":
        if before == "Concluído":
            return jsonify(error="Um chamado concluído não pode ser reaberto neste MVP."), 409
        connection.execute(
            """UPDATE tickets SET status='Em atendimento',assigned_to_id=?,updated_at=?
               WHERE id=?""",
            (assigned_to, now_iso(), ticket_id),
        )
        add_event(
            connection,
            ticket_id,
            g.user["id"],
            "status",
            "A equipe técnica iniciou o atendimento.",
            before,
            "Em atendimento",
        )
        notify_user(
            connection,
            ticket["requester_id"],
            ticket_id,
            "Chamado em atendimento",
            f"A equipe começou a tratar o chamado {ticket['protocol']}.",
        )
    elif action == "estimate":
        estimate = clean_text(data.get("estimated_at"), 40)
        if estimate:
            try:
                datetime.fromisoformat(estimate)
            except ValueError:
                return jsonify(error="Informe uma previsão válida."), 400
        connection.execute(
            "UPDATE tickets SET estimated_at=?,assigned_to_id=?,updated_at=? WHERE id=?",
            (estimate or None, assigned_to, now_iso(), ticket_id),
        )
        add_event(
            connection,
            ticket_id,
            g.user["id"],
            "estimate",
            f"Previsão de atendimento atualizada para {estimate or 'não informada'}.",
        )
    elif action == "close":
        if before == "Concluído":
            return jsonify(error="Este chamado já está concluído."), 409
        summary = clean_text(data.get("message"), 1000)
        if not summary:
            return jsonify(error="Registre um resumo do atendimento."), 400
        closed = now_iso()
        connection.execute(
            """UPDATE tickets SET status='Concluído',assigned_to_id=?,updated_at=?,closed_at=?
               WHERE id=?""",
            (assigned_to, closed, closed, ticket_id),
        )
        add_event(
            connection,
            ticket_id,
            g.user["id"],
            "close",
            summary,
            before,
            "Concluído",
        )
        notify_user(
            connection,
            ticket["requester_id"],
            ticket_id,
            "Atendimento concluído",
            f"O chamado {ticket['protocol']} foi concluído. Resumo: {summary}",
        )
    else:
        return jsonify(error="Ação desconhecida."), 400
    connection.commit()
    return jsonify(ok=True)


@app.get("/api/notifications")
@login_required
def api_notifications():
    rows = get_db().execute(
        """SELECT * FROM notifications WHERE user_id=?
           ORDER BY id DESC LIMIT 30""",
        (g.user["id"],),
    ).fetchall()
    unread = get_db().execute(
        "SELECT COUNT(*) AS count FROM notifications WHERE user_id=? AND read_at IS NULL",
        (g.user["id"],),
    ).fetchone()["count"]
    return jsonify(unread=unread, items=[dict(row) for row in rows])


@app.post("/api/notifications/<int:notification_id>/read")
@login_required
def api_notification_read(notification_id: int):
    csrf_required()
    get_db().execute(
        """UPDATE notifications SET read_at=? WHERE id=? AND user_id=?""",
        (now_iso(), notification_id, g.user["id"]),
    )
    get_db().commit()
    return jsonify(ok=True)


@app.put("/api/profile/contact")
@login_required
def api_update_contact():
    csrf_required()
    data = json_body()
    email = clean_text(data.get("email"), 180).lower() or None
    phone = clean_text(data.get("phone"), 30) or None
    if not email and not phone:
        return jsonify(error="Mantenha pelo menos um contato: e-mail ou telefone."), 400
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Confira o formato do e-mail."), 400
    if phone and len(re.sub(r"\D", "", phone)) < 10:
        return jsonify(error="Confira o telefone informado."), 400
    get_db().execute(
        "UPDATE users SET email=?,phone=? WHERE id=?",
        (email, phone, g.user["id"]),
    )
    get_db().commit()
    return jsonify(ok=True)


@app.errorhandler(400)
def bad_request(error):
    if request.path.startswith("/api/"):
        return jsonify(error=getattr(error, "description", "Requisição inválida.")), 400
    return render_template("error.html", code=400, message="Não foi possível concluir esta ação."), 400


@app.errorhandler(403)
def forbidden(_error):
    if request.path.startswith("/api/"):
        return jsonify(error="Você não tem permissão para esta ação."), 403
    return render_template("error.html", code=403, message="Acesso não permitido."), 403


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify(error="Chamado não encontrado."), 404
    return render_template("error.html", code=404, message="Página ou chamado não encontrado."), 404


if __name__ == "__main__":
    init_db()
    app.run(
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", os.environ.get("APP_PORT", "5000"))),
        debug=False,
    )



