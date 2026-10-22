from functools import wraps

from flask import abort, g, redirect, render_template, request, session, url_for
from supabase_auth.errors import AuthApiError

from app import app
from app.repositories import LegacyProfileError, create_job, ensure_profile, get_job, list_jobs
from app.supabase_client import create_supabase_client


def remember_tokens(auth_session):
    session['sb_access_token'] = auth_session.access_token
    session['sb_refresh_token'] = auth_session.refresh_token


def finish_login(client, response):
    if not response.session:
        raise ValueError('Confirme seu e-mail e faça login.')
    verified = client.auth.get_user(response.session.access_token).user
    if not verified:
        raise ValueError('Não foi possível verificar a sessão.')
    profile = ensure_profile(client, verified)
    # Tokens ficam na sessão do servidor; o cookie contém somente seu identificador.
    session.clear()
    session['auth_user_id'] = str(verified.id)
    app.session_interface.regenerate(session)
    session.permanent = True
    remember_tokens(response.session)
    session['user_email'] = verified.email
    session['user_name'] = profile.get('nome') or verified.email.split('@')[0]
    session['user_role'] = 'RH'
    session['user_initials'] = ''.join(part[0] for part in session['user_name'].split()[:2]).upper()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('sb_access_token') or not session.get('sb_refresh_token'):
            return redirect(url_for('login'))
        try:
            client = create_supabase_client()
            response = client.auth.set_session(session['sb_access_token'], session['sb_refresh_token'])
            if not response.session:
                session.clear()
                return redirect(url_for('login'))
            remember_tokens(response.session)
            user = client.auth.get_user(response.session.access_token).user
            if not user or str(user.id) != session.get('auth_user_id'):
                session.clear()
                return redirect(url_for('login'))
        except AuthApiError:
            session.clear()
            return redirect(url_for('login'))
        except Exception as error:
            app.logger.warning('Serviço de autenticação indisponível: %s', type(error).__name__)
            abort(503, description='Não foi possível verificar seu acesso. Tente novamente.')
        try:
            g.supabase = client
            g.profile = ensure_profile(client, user)
        except LegacyProfileError:
            abort(409, description='Perfil antigo: peça à equipe para vincular seu e-mail ao Supabase Auth.')
        except Exception as error:
            app.logger.warning('Falha de acesso ao perfil: %s', type(error).__name__)
            abort(503, description='Não foi possível acessar seu perfil. Confira a migração do banco.')
        return view(*args, **kwargs)
    return wrapped


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', error=None)
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    if not email or not password:
        return render_template('login.html', error='Informe e-mail e senha.'), 400
    try:
        client = create_supabase_client()
        response = client.auth.sign_in_with_password({'email': email, 'password': password})
        finish_login(client, response)
    except AuthApiError:
        return render_template('login.html', error='Não foi possível entrar. Confira as credenciais e a confirmação do e-mail.'), 401
    except LegacyProfileError:
        return render_template('login.html', error='Seu perfil antigo precisa ser vinculado ao Supabase Auth pela equipe.'), 409
    except Exception as error:
        app.logger.warning('Falha no login: %s', type(error).__name__)
        return render_template('login.html', error='Não foi possível concluir o login. Confira a conexão e a migração do banco.'), 503
    return redirect(url_for('dashboard'))


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'GET':
        return render_template('cadastro.html', error=None)
    name = request.form.get('name', '').strip()
    company = request.form.get('company', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm = request.form.get('password_confirm', '')
    if not all([name, company, email, password, confirm]):
        return render_template('cadastro.html', error='Preencha todos os campos.'), 400
    if password != confirm:
        return render_template('cadastro.html', error='As senhas não coincidem.'), 400
    if len(password) < 8:
        return render_template('cadastro.html', error='Use uma senha com pelo menos 8 caracteres.'), 400
    try:
        client = create_supabase_client()
        response = client.auth.sign_up({
            'email': email, 'password': password,
            'options': {'data': {'name': name[:120], 'company': company[:120]}},
        })
        if not response.session:
            return render_template('login.html', error='Solicitação recebida. Se necessário, confirme o e-mail enviado pelo Supabase e depois faça login.')
        finish_login(client, response)
    except AuthApiError:
        return render_template('cadastro.html', error='Não foi possível cadastrar. Confira o e-mail e as regras de senha; se já tem conta, tente entrar.'), 400
    except Exception as error:
        app.logger.warning('Falha no cadastro: %s', type(error).__name__)
        return render_template('login.html', error='Não foi possível concluir o perfil. A conta pode ter sido criada: tente entrar antes de repetir o cadastro.'), 503
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    try:
        if session.get('sb_access_token') and session.get('sb_refresh_token'):
            client = create_supabase_client()
            client.auth.set_session(session['sb_access_token'], session['sb_refresh_token'])
            client.auth.sign_out({'scope': 'local'})
    except Exception:
        app.logger.warning('Não foi possível revogar a sessão remota no logout.')
    finally:
        session.clear()
    return redirect(url_for('login'))


def database_jobs():
    try:
        return list_jobs(g.supabase)
    except Exception as error:
        app.logger.warning('Falha na consulta de vagas: %s', type(error).__name__)
        abort(503, description='Não foi possível consultar as vagas. Confira o banco e o RLS.')


def database_job(job_id):
    try:
        identifier = int(job_id)
        if identifier <= 0:
            raise ValueError
    except (TypeError, ValueError):
        abort(404)
    try:
        job = get_job(g.supabase, identifier)
    except Exception as error:
        app.logger.warning('Falha ao abrir vaga: %s', type(error).__name__)
        abort(503, description='Não foi possível abrir a vaga.')
    if job is None:
        abort(404, description='Vaga não encontrada ou sem acesso.')
    return job


@app.route('/')
@login_required
def dashboard():
    jobs = database_jobs()
    return render_template('dashboard.html', active_page='dashboard', jobs=jobs,
                           open_jobs_count=sum(job['status']=='Aberta' for job in jobs),
                           total_resumes='—', avg_match_rate='—')


@app.route('/nova-vaga', methods=['GET', 'POST'])
@login_required
def nova_vaga():
    if request.method == 'POST':
        try:
            create_job(g.supabase, g.profile['id'],
                       request.form.get('title', ''), request.form.get('description', ''))
        except ValueError as error:
            abort(400, description=str(error))
        except Exception as error:
            app.logger.warning('Falha ao gravar vaga: %s', type(error).__name__)
            abort(503, description='Não foi possível confirmar a gravação. Confira o dashboard antes de reenviar.')
        return redirect(url_for('dashboard'))
    return render_template('nova_vaga.html', active_page='vagas')


@app.route('/vagas')
@app.route('/vagas/<job_id>')
@login_required
def vagas(job_id=None):
    if job_id is None:
        return redirect(url_for('nova_vaga'))
    job = database_job(job_id)
    return render_template('vagas.html', active_page='candidatos', job=job,
                           jobs=database_jobs(), candidates=[])


@app.route('/candidatos')
@login_required
def candidatos():
    jobs = database_jobs()
    return redirect(url_for('vagas', job_id=jobs[0]['id'])) if jobs else redirect(url_for('nova_vaga'))


@app.route('/configuracoes')
@login_required
def configuracoes():
    return render_template('configuracoes.html', active_page='configuracoes')


@app.route('/vagas/<job_id>/adicionar-curriculos', methods=['GET', 'POST'])
@login_required
def adicionar_curriculos(job_id):
    job = database_job(job_id)
    if request.method == 'POST':
        abort(501, description='Vaga salva no banco. Upload e análise de currículos ainda aguardam a próxima integração; nenhum candidato foi criado.')
    return render_template('adicionar_curriculos.html', active_page='candidatos',
                           job=job, jobs=database_jobs(), candidates=[])


@app.route('/vagas/<job_id>/candidato/<candidate_id>')
@login_required
def candidato_detalhe(job_id, candidate_id):
    database_job(job_id)
    abort(404, description='Nenhum candidato foi integrado a esta vaga nesta etapa.')


@app.route('/vagas/<job_id>/candidato/<candidate_id>/status', methods=['POST'])
@login_required
def atualizar_status_candidato(job_id, candidate_id):
    database_job(job_id)
    abort(501, description='Persistência de candidatos ainda não integrada.')
