from flask import render_template, request, redirect, url_for, session
from functools import wraps
from app import app

JOBS = [
    {"id": "1", "title": "Desenvolvedor Backend Python", "created_at": "10/09/2026", "candidate_count": 45, "status": "Aberta"},
    {"id": "2", "title": "Engenheiro de Dados Sênior", "created_at": "07/09/2026", "candidate_count": 28, "status": "Aberta"},
    {"id": "3", "title": "Product Designer UX/UI", "created_at": "02/09/2026", "candidate_count": 61, "status": "Aberta"},
    {"id": "4", "title": "DevOps / SRE Pleno", "created_at": "20/08/2026", "candidate_count": 19, "status": "Encerrada"},
    {"id": "5", "title": "Tech Lead Frontend React", "created_at": "15/08/2026", "candidate_count": 33, "status": "Encerrada"},
]

CANDIDATES_BY_JOB = {
    "1": [
        {
            "id": "1", "name": "Lucas Ferreira Santos", "initials": "LF", "score": 92,
            "email": "lucas.ferreira@email.com", "phone": "(11) 99821-4430",
            "education": "Bacharelado em Ciência da Computação — USP", "last_role": "Backend Engineer @ Nubank",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
            "met": ["Python 3.10+", "FastAPI ou Django REST", "PostgreSQL", "Docker / Kubernetes", "Testes unitários", "Inglês técnico"],
            "missing": ["Experiência com AWS Lambda", "Conhecimento em Kafka"],
        },
        {
            "id": "2", "name": "Mariana Oliveira Costa", "initials": "MO", "score": 87,
            "email": "mariana.costa@email.com", "phone": "(21) 98745-3310",
            "education": "Mestrado em Engenharia de Software — UNICAMP", "last_role": "Senior Python Dev @ iFood",
            "skills": ["Python", "Django", "MySQL", "Kubernetes", "Celery"],
            "met": ["Python 3.10+", "Docker / Kubernetes", "Testes unitários", "Inglês técnico", "PostgreSQL"],
            "missing": ["FastAPI ou Django REST", "Experiência com AWS Lambda"],
        },
        {
            "id": "3", "name": "Rafael Almeida Nunes", "initials": "RA", "score": 71,
            "email": "rafael.nunes@email.com", "phone": "(31) 97632-8821",
            "education": "Tecnólogo em Sistemas para Internet — PUC Minas", "last_role": "Backend Dev @ Totvs",
            "skills": ["Python", "Flask", "MongoDB", "Docker"],
            "met": ["Python 3.10+", "Docker / Kubernetes", "Testes unitários"],
            "missing": ["FastAPI ou Django REST", "PostgreSQL", "Experiência com AWS Lambda", "Kafka", "Inglês técnico"],
        },
        {
            "id": "4", "name": "Juliana Pereira Lima", "initials": "JP", "score": 58,
            "email": "juliana.lima@email.com", "phone": "(85) 99012-5567",
            "education": "Bacharelado em Sistemas de Informação — UFC", "last_role": "Python Developer @ Hapvida",
            "skills": ["Python", "Flask", "SQLite"],
            "met": ["Python 3.10+", "Testes unitários"],
            "missing": ["FastAPI ou Django REST", "PostgreSQL", "Docker / Kubernetes", "AWS Lambda", "Kafka", "Inglês técnico"],
        },
        {
            "id": "5", "name": "André Souza Cardoso", "initials": "AS", "score": 44,
            "email": "andre.cardoso@email.com", "phone": "(51) 98301-7734",
            "education": "Bacharelado em Engenharia da Computação — PUCRS", "last_role": "Junior Backend Dev @ Dell",
            "skills": ["Python", "Django"],
            "met": ["Python 3.10+"],
            "missing": ["FastAPI", "PostgreSQL", "Docker", "AWS", "Kafka", "Testes unitários", "Inglês técnico"],
        },
    ],
}


def get_job_or_first(job_id):
    job = next((j for j in JOBS if j["id"] == job_id), None)
    return job or JOBS[0]


USERS = {
    "carlos@nexora.com": {"password": "123456", "name": "Carlos Andrade", "role": "RH Sênior"}
}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = USERS.get(email)
        if user and user["password"] == password:
            session["user_email"] = email
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]
            session["user_initials"] = "".join(p[0] for p in user["name"].split()[:2]).upper()
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="E-mail ou senha inválidos.")
    return render_template("login.html", error=None)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        company = request.form.get("company", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not all([name, company, email, password, password_confirm]):
            return render_template("cadastro.html", error="Preencha todos os campos.")
        if password != password_confirm:
            return render_template("cadastro.html", error="As senhas não coincidem.")
        if email in USERS:
            return render_template("cadastro.html", error="Já existe uma conta com este e-mail.")

        USERS[email] = {"password": password, "name": name, "role": "RH"}
        session["user_email"] = email
        session["user_name"] = name
        session["user_role"] = "RH"
        session["user_initials"] = "".join(p[0] for p in name.split()[:2]).upper()
        return redirect(url_for("dashboard"))

    return render_template("cadastro.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    open_jobs_count = sum(1 for j in JOBS if j["status"] == "Aberta")
    total_resumes = sum(j["candidate_count"] for j in JOBS)
    return render_template(
        "dashboard.html",
        active_page="dashboard",
        jobs=JOBS,
        open_jobs_count=open_jobs_count,
        total_resumes=total_resumes,
        avg_match_rate=73,
    )


@app.route("/vagas")
@app.route("/vagas/<job_id>")
@login_required
def vagas(job_id="1"):
    job = get_job_or_first(job_id)
    candidates = CANDIDATES_BY_JOB.get(job["id"], [])
    return render_template("vagas.html", active_page="vagas", job=job, candidates=candidates)

@app.route("/vagas/<job_id>/candidato/<candidate_id>")
@login_required
def candidato_detalhe(job_id, candidate_id):
    job = get_job_or_first(job_id)
    candidate = get_candidate_or_404(job["id"], candidate_id)
    if candidate is None:
        return redirect(url_for("vagas", job_id=job["id"]))
    return render_template("candidato.html", active_page="vagas", job=job, candidate=candidate)

def get_candidate_or_404(job_id, candidate_id):
    candidates = CANDIDATES_BY_JOB.get(job_id, [])
    return next((c for c in candidates if c["id"] == candidate_id), None)


@app.route("/configuracoes")
@login_required
def configuracoes():
    return render_template("configuracoes.html", active_page="configuracoes")

@app.route("/vagas/<job_id>/adicionar-curriculos", methods=["GET", "POST"])
@login_required
def adicionar_curriculos(job_id):
    job = get_job_or_first(job_id)
    if request.method == "POST":
        # Aqui depois entra a lógica real: salvar os arquivos enviados e
        # rodar a IA para calcular a aderência de cada currículo com a vaga.
        # Por enquanto, só redireciona de volta para o ranking da vaga.
        return redirect(url_for("vagas", job_id=job["id"]))
    return render_template("adicionar_curriculos.html", active_page="vagas", job=job, jobs=JOBS)