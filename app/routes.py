from flask import render_template, request, redirect, url_for, session
from functools import wraps
from datetime import datetime
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
            "filename": "cv_lucas_ferreira.pdf", "submitted_at": "18/10/2026", "status": "Analisado",
            "email": "lucas.ferreira@email.com", "phone": "(11) 99821-4430",
            "education": "Bacharelado em Ciência da Computação — USP", "last_role": "Backend Engineer @ Nubank",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
            "met": ["Python 3.10+", "FastAPI ou Django REST", "PostgreSQL", "Docker / Kubernetes", "Testes unitários", "Inglês técnico"],
            "missing": ["Experiência com AWS Lambda", "Conhecimento em Kafka"],
        },
        {
            "id": "2", "name": "Mariana Oliveira Costa", "initials": "MO", "score": 87,
            "filename": "curriculo_mariana_costa_2026.docx", "submitted_at": "16/10/2026", "status": "Aprovado",
            "email": "mariana.costa@email.com", "phone": "(21) 98745-3310",
            "education": "Mestrado em Engenharia de Software — UNICAMP", "last_role": "Senior Python Dev @ iFood",
            "skills": ["Python", "Django", "MySQL", "Kubernetes", "Celery"],
            "met": ["Python 3.10+", "Docker / Kubernetes", "Testes unitários", "Inglês técnico", "PostgreSQL"],
            "missing": ["FastAPI ou Django REST", "Experiência com AWS Lambda"],
        },
        {
            "id": "3", "name": "Rafael Almeida Nunes", "initials": "RA", "score": 71,
            "filename": "rafael_nunes_backend.pdf", "submitted_at": "12/10/2026", "status": "Analisado",
            "email": "rafael.nunes@email.com", "phone": "(31) 97632-8821",
            "education": "Tecnólogo em Sistemas para Internet — PUC Minas", "last_role": "Backend Dev @ Totvs",
            "skills": ["Python", "Flask", "MongoDB", "Docker"],
            "met": ["Python 3.10+", "Docker / Kubernetes", "Testes unitários"],
            "missing": ["FastAPI ou Django REST", "PostgreSQL", "Experiência com AWS Lambda", "Kafka", "Inglês técnico"],
        },
        {
            "id": "4", "name": "Juliana Pereira Lima", "initials": "JP", "score": 58,
            "filename": "cv_juliana_lima_dev.pdf", "submitted_at": "09/10/2026", "status": "Descartado",
            "email": "juliana.lima@email.com", "phone": "(85) 99012-5567",
            "education": "Bacharelado em Sistemas de Informação — UFC", "last_role": "Python Developer @ Hapvida",
            "skills": ["Python", "Flask", "SQLite"],
            "met": ["Python 3.10+", "Testes unitários"],
            "missing": ["FastAPI ou Django REST", "PostgreSQL", "Docker / Kubernetes", "AWS Lambda", "Kafka", "Inglês técnico"],
        },
        {
            "id": "5", "name": "André Souza Cardoso", "initials": "AS", "score": 44,
            "filename": "andre_cardoso_junior.pdf", "submitted_at": "04/10/2026", "status": "Pendente",
            "email": "andre.cardoso@email.com", "phone": "(51) 98301-7734",
            "education": "Bacharelado em Engenharia da Computação — PUCRS", "last_role": "Junior Backend Dev @ Dell",
            "skills": ["Python", "Django"],
            "met": ["Python 3.10+"],
            "missing": ["FastAPI", "PostgreSQL", "Docker", "AWS", "Kafka", "Testes unitários", "Inglês técnico"],
        },
    ],
    "2": [
        {
            "id": "201", "name": "Beatriz Rocha Mendes", "initials": "BR", "score": 94,
            "filename": "beatriz_rocha_data_engineer.pdf", "submitted_at": "19/10/2026", "status": "Aprovado",
            "email": "beatriz.rocha@email.com", "phone": "(11) 97123-9988",
            "education": "Mestrado em Ciência da Computação — USP", "last_role": "Lead Data Engineer @ QuintoAndar",
            "skills": ["Python", "Apache Spark", "Airflow", "Kafka", "Snowflake", "AWS"],
            "met": ["Python avançado", "Spark / PySpark", "Airflow", "Cloud AWS", "Data Lake / Snowflake"],
            "missing": ["Databricks Delta Live Tables"],
        },
        {
            "id": "202", "name": "Thiago Martins Vieira", "initials": "TM", "score": 78,
            "filename": "thiago_vieira_dados.docx", "submitted_at": "15/10/2026", "status": "Analisado",
            "email": "thiago.vieira@email.com", "phone": "(31) 98877-6655",
            "education": "Bacharelado em Estatística — UFMG", "last_role": "Data Engineer Pleno @ Hotmart",
            "skills": ["Python", "SQL", "Airflow", "PostgreSQL", "GCP"],
            "met": ["Python avançado", "SQL analítico", "Orquestração com Airflow"],
            "missing": ["Experiência prévia em AWS", "Kafka em tempo real"],
        },
        {
            "id": "203", "name": "Camila Figueiredo", "initials": "CF", "score": 62,
            "filename": "camila_figueiredo_cv.pdf", "submitted_at": "10/10/2026", "status": "Pendente",
            "email": "camila.figueiredo@email.com", "phone": "(41) 99123-4567",
            "education": "Sistemas de Informação — UFPR", "last_role": "Analista de BI Sênior @ O Boticário",
            "skills": ["SQL", "Power BI", "Python", "ETL"],
            "met": ["SQL analítico", "ETL"],
            "missing": ["Spark / PySpark", "Airflow", "Kafka", "Infraestrutura Cloud"],
        },
    ],
    "3": [
        {
            "id": "301", "name": "Felipe Cavalcante", "initials": "FC", "score": 91,
            "filename": "felipe_cavalcante_uxui.pdf", "submitted_at": "17/10/2026", "status": "Analisado",
            "email": "felipe.cavalcante@email.com", "phone": "(11) 98456-1122",
            "education": "Design Digital — Anhembi Morumbi", "last_role": "Senior Product Designer @ C6 Bank",
            "skills": ["Figma", "Design System", "User Research", "Prototyping", "Design Ops"],
            "met": ["Figma avançado", "Construção de Design System", "Pesquisa qualitativa e quantitativa"],
            "missing": ["Noções básicas de front-end HTML/CSS"],
        },
        {
            "id": "302", "name": "Larissa Dornelles", "initials": "LD", "score": 83,
            "filename": "larissa_dornelles_designer.pdf", "submitted_at": "14/10/2026", "status": "Pendente",
            "email": "larissa.dornelles@email.com", "phone": "(51) 99882-3344",
            "education": "Comunicação e Design — UFRGS", "last_role": "Product Designer @ Stone",
            "skills": ["Figma", "UI Design", "User Testing", "Miro"],
            "met": ["Figma avançado", "Testes de usabilidade"],
            "missing": ["Liderança de Design System multiplataforma"],
        },
    ]
}

def get_job_or_first(job_id):
    job = next((j for j in JOBS if j["id"] == str(job_id)), None)
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
    total_resumes = sum(len(cands) for cands in CANDIDATES_BY_JOB.values())
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
def vagas(job_id=None):
    if job_id is None:
        return redirect(url_for("nova_vaga"))
    
    job = get_job_or_first(job_id)
    candidates = CANDIDATES_BY_JOB.get(job["id"], [])
    return render_template(
        "vagas.html",
        active_page="candidatos",
        job=job,
        jobs=JOBS,
        candidates=candidates
    )


@app.route("/candidatos")
@login_required
def candidatos():
    return redirect(url_for("vagas", job_id="1"))


@app.route("/vagas/<job_id>/candidato/<candidate_id>")
@login_required
def candidato_detalhe(job_id, candidate_id):
    job = get_job_or_first(job_id)
    candidate = get_candidate_or_404(job["id"], candidate_id)
    if candidate is None:
        return redirect(url_for("vagas", job_id=job["id"]))
    return render_template("candidato.html", active_page="candidatos", job=job, candidate=candidate)


@app.route("/vagas/<job_id>/candidato/<candidate_id>/status", methods=["POST"])
@login_required
def atualizar_status_candidato(job_id, candidate_id):
    novo_status = request.form.get("status")
    candidate = get_candidate_or_404(str(job_id), str(candidate_id))
    if candidate and novo_status in ["Aprovado", "Descartado", "Analisado", "Pendente"]:
        candidate["status"] = novo_status
    return redirect(url_for("candidato_detalhe", job_id=job_id, candidate_id=candidate_id))


def get_candidate_or_404(job_id, candidate_id):
    candidates = CANDIDATES_BY_JOB.get(str(job_id), [])
    return next((c for c in candidates if str(c["id"]) == str(candidate_id)), None)


@app.route("/configuracoes")
@login_required
def configuracoes():
    return render_template("configuracoes.html", active_page="configuracoes")


@app.route("/vagas/<job_id>/adicionar-curriculos", methods=["GET", "POST"])
@login_required
def adicionar_curriculos(job_id):
    target_job_id = request.form.get("job_id", job_id) if request.method == "POST" else job_id
    job = get_job_or_first(target_job_id)
    candidates_list = CANDIDATES_BY_JOB.setdefault(str(job["id"]), [])

    if request.method == "POST":
        selected_ids = request.form.getlist("selected_candidates")
        uploaded_files = request.files.getlist("files")

        # 1. Atualiza o status dos candidatos selecionados para 'Analisado'
        for cand in candidates_list:
            if str(cand["id"]) in selected_ids and cand.get("status") == "Pendente":
                cand["status"] = "Analisado"

        # 2. Processa novos arquivos enviados se houver
        today_str = datetime.now().strftime("%d/%m/%Y")
        for f in uploaded_files:
            if f and f.filename and f.filename.strip():
                clean_name = f.filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
                initials = "".join(part[0] for part in clean_name.split()[:2]).upper() or "CV"
                new_cand_id = str(len(candidates_list) + 100)
                candidates_list.insert(0, {
                    "id": new_cand_id,
                    "name": clean_name,
                    "initials": initials,
                    "score": 80,
                    "filename": f.filename,
                    "submitted_at": today_str,
                    "status": "Analisado",
                    "email": f"{clean_name.lower().replace(' ', '.')}@email.com",
                    "phone": "(11) 99000-0000",
                    "education": "Formação Extraída via IA",
                    "last_role": "Experiência Profissional Analisada",
                    "skills": ["Python", "FastAPI", "SQL"],
                    "met": ["Requisitos Básicos da Vaga", "Formação Compatível"],
                    "missing": ["Certificação Específica"],
                })

        # Atualiza a contagem de candidatos da vaga
        job["candidate_count"] = len(candidates_list)
        return redirect(url_for("vagas", job_id=job["id"]))

    return render_template(
        "adicionar_curriculos.html",
        active_page="candidatos",
        job=job,
        jobs=JOBS,
        candidates=candidates_list
    )


@app.route("/nova-vaga", methods=["GET", "POST"])
@login_required
def nova_vaga():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        
        nova_vaga_id = str(len(JOBS) + 1)
        JOBS.insert(0, {
            "id": nova_vaga_id,
            "title": title,
            "created_at": datetime.now().strftime("%d/%m/%Y"),
            "candidate_count": 0,
            "status": "Aberta"
        })
        CANDIDATES_BY_JOB[nova_vaga_id] = []
        
        return redirect(url_for("dashboard"))

    return render_template("nova_vaga.html", active_page="vagas")
