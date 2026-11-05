import re
from functools import wraps

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from supabase_auth.errors import AuthApiError

from app import app
from app.repositories import (
    LegacyProfileError,
    create_job,
    create_resume,
    ensure_profile,
    get_job,
    get_resume,
    list_jobs,
    list_resumes,
    update_job,
    update_profile,
    update_resume_status,
)
from app.requisitos import NIVEIS, STATUS_VAGA, TIPOS, build_requirements, rows_from_form
from app.supabase_client import create_supabase_client
from src.data.clean import parse_resume_pdf


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
    total_resumes = sum(job.get('candidate_count', 0) for job in jobs)
    return render_template('dashboard.html', active_page='dashboard', jobs=jobs,
                           open_jobs_count=sum(job['status'] == 'Aberta' for job in jobs),
                           total_resumes=total_resumes if total_resumes else '—', avg_match_rate='—')


def read_job_form(known_ids=(), next_id=None):
    form = request.form
    values = {
        'title': form.get('title', '').strip(),
        'description': form.get('description', '').strip(),
        'status': form.get('status', 'Aberta').strip(),
        'requirements': [],
    }
    requirements = error = None
    try:
        if 'req_text' in form:
            values['requirements'] = rows_from_form(form)
            requirements = build_requirements(values['requirements'], known_ids, next_id)
    except ValueError as exc:
        error = str(exc)
    return values, requirements, error


@app.route('/nova-vaga', methods=['GET', 'POST'])
@login_required
def nova_vaga():
    values = {'title': '', 'description': '', 'status': 'Aberta', 'requirements': []}
    error = None
    if request.method == 'POST':
        values, requirements, error = read_job_form()
        if not error:
            try:
                job = create_job(g.supabase, g.profile['id'],
                                 values['title'], values['description'], requirements)
            except ValueError as exc:
                error = str(exc)
            except Exception as exc:
                app.logger.warning('Falha ao gravar vaga: %s', type(exc).__name__)
                abort(503, description='Não foi possível confirmar a gravação. Confira o dashboard antes de reenviar.')
            else:
                return redirect(url_for('vagas', job_id=job['id']))
        return render_template('nova_vaga.html', active_page='vagas', form=values, error=error,
                               tipos=TIPOS, niveis=NIVEIS, status_options=STATUS_VAGA), 400
    return render_template('nova_vaga.html', active_page='vagas', form=values, error=None,
                           tipos=TIPOS, niveis=NIVEIS, status_options=STATUS_VAGA)


@app.route('/vagas')
@app.route('/vagas/<job_id>')
@login_required
def vagas(job_id=None):
    jobs = database_jobs()
    if job_id is None:
        return redirect(url_for('vagas', job_id=jobs[0]['id'])) if jobs else redirect(url_for('nova_vaga'))
    job = database_job(job_id)
    candidates = list_resumes(g.supabase, job['id'])
    return render_template('vagas.html', active_page='candidatos', job=job,
                           jobs=jobs, candidates=candidates)


@app.route('/vagas/<job_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_vaga(job_id):
    job = database_job(job_id)
    previous_items = job['requirements_data']['items']
    values = {
        'title': job['title'],
        'description': job['description'],
        'status': job['status'],
        'requirements': previous_items,
    }
    error = None
    if request.method == 'POST':
        values, requirements, error = read_job_form([item['id'] for item in previous_items],
                                                  job['requirements_data'].get('proximo_id'))
        if not error:
            try:
                update_job(g.supabase, job['id'], values['title'], values['description'],
                           values['status'], requirements)
            except ValueError as exc:
                error = str(exc)
            except LookupError:
                app.logger.warning('Edição sem linhas alteradas: falta a política de UPDATE?')
                abort(503, description='Não foi possível salvar a vaga. Confira se a migração sql/002_editar_vagas.sql foi executada no Supabase.')
            except Exception as exc:
                app.logger.warning('Falha ao atualizar vaga: %s', type(exc).__name__)
                abort(503, description='Não foi possível confirmar a alteração. Reabra a vaga antes de reenviar.')
            else:
                return redirect(url_for('vagas', job_id=job['id']))
        return render_template('editar_vaga.html', active_page='candidatos', form=values, error=error,
                               job=job, tipos=TIPOS, niveis=NIVEIS, status_options=STATUS_VAGA), 400
    return render_template('editar_vaga.html', active_page='candidatos', form=values, error=None,
                           job=job, tipos=TIPOS, niveis=NIVEIS, status_options=STATUS_VAGA)


@app.route('/candidatos')
@login_required
def candidatos():
    jobs = database_jobs()
    return redirect(url_for('vagas', job_id=jobs[0]['id'])) if jobs else redirect(url_for('nova_vaga'))


@app.route('/configuracoes')
@login_required
def configuracoes():
    return redirect(url_for('editar_perfil'))


@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    form = {
        'name': g.profile.get('nome') or '',
        'email': g.profile.get('email') or '',
        'company': g.profile.get('empresa') or '',
    }
    if request.method == 'POST':
        form.update({
            'name': request.form.get('name', '').strip(),
            'email': request.form.get('email', '').strip().lower(),
            'company': request.form.get('company', '').strip(),
        })
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        error = None

        if not all(form.values()):
            error = 'Preencha nome, e-mail e empresa.'
        elif len(form['name']) > 120 or len(form['company']) > 120:
            error = 'Nome e empresa devem ter no máximo 120 caracteres.'
        elif len(form['email']) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', form['email']):
            error = 'Informe um endereço de e-mail válido.'
        elif password and password != password_confirm:
            error = 'As senhas não coincidem.'
        elif password and (len(password) < 8 or len(password) > 128):
            error = 'A nova senha deve ter entre 8 e 128 caracteres.'

        if error:
            return render_template('editar_perfil.html', active_page='configuracoes',
                                   form=form, error=error), 400

        profile_changes = {}
        if form['name'] != (g.profile.get('nome') or ''):
            profile_changes['nome'] = form['name']
        if form['company'] != (g.profile.get('empresa') or ''):
            profile_changes['empresa'] = form['company']
        if form['email'] != (g.profile.get('email') or '').lower():
            profile_changes['email'] = form['email']

        attributes = {}
        if 'nome' in profile_changes or 'empresa' in profile_changes:
            attributes['data'] = {'name': form['name'], 'company': form['company']}
        if 'email' in profile_changes:
            attributes['email'] = form['email']
        if password:
            attributes['password'] = password

        try:
            if attributes:
                response = g.supabase.auth.update_user(attributes)
                if not response.user:
                    raise RuntimeError('Supabase não retornou o usuário atualizado.')
                if 'email' in profile_changes:
                    effective_email = (response.user.email or g.profile['email']).lower()
                    profile_changes['email'] = effective_email
            updated_profile = g.profile
            if profile_changes:
                updated_profile = update_profile(
                    g.supabase, g.profile['id'], session['auth_user_id'], profile_changes,
                )
        except AuthApiError:
            return render_template(
                'editar_perfil.html', active_page='configuracoes', form=form,
                error='Não foi possível atualizar o perfil. Confira o e-mail e os requisitos da nova senha.',
            ), 400
        except Exception as error:
            app.logger.warning(
                'Falha ao atualizar perfil (%s, código=%s): %s',
                type(error).__name__,
                getattr(error, 'code', None),
                getattr(error, 'message', str(error)),
            )
            abort(503, description='Não foi possível confirmar a atualização do perfil. Reabra a tela antes de tentar novamente.')

        g.profile = updated_profile
        session['user_name'] = updated_profile['nome']
        session['user_email'] = updated_profile['email']
        session['user_initials'] = ''.join(part[0] for part in updated_profile['nome'].split()[:2]).upper()
        if updated_profile['email'] != form['email']:
            flash('Perfil atualizado. Confirme o link enviado ao novo e-mail para concluir a alteração.', 'success')
        else:
            flash('Perfil atualizado com sucesso.', 'success')
        return redirect(url_for('editar_perfil'))

    return render_template('editar_perfil.html', active_page='configuracoes', form=form, error=None)


@app.route('/vagas/<job_id>/adicionar-curriculos', methods=['GET', 'POST'])
@login_required
def adicionar_curriculos(job_id):
    job = database_job(job_id)
    candidates = list_resumes(g.supabase, job['id'])

    if request.method == 'POST':
        uploaded = request.files.getlist('files')
        valid_files = [f for f in uploaded if f and f.filename and f.filename.strip()]
        selected_ids = set(request.form.getlist('selected_candidates'))

        if not valid_files and not selected_ids:
            abort(400, description='Selecione ao menos um arquivo PDF ou currículo existente.')

        for cid in selected_ids:
            try:
                update_resume_status(g.supabase, job['id'], cid, 'Analisado')
            except Exception as error:
                app.logger.warning('Falha ao atualizar status do candidato %s: %s', cid, type(error).__name__)

        for file_storage in valid_files:
            lower_name = file_storage.filename.lower()
            if not lower_name.endswith('.pdf'):
                abort(400, description=f'Arquivo inválido: {file_storage.filename}. Envie arquivos no formato PDF.')
            try:
                parsed = parse_resume_pdf(file_storage, filename=file_storage.filename)
            except Exception as error:
                app.logger.warning('Falha ao processar PDF %s: %s', file_storage.filename, type(error).__name__)
                abort(400, description=f'Não foi possível extrair texto de {file_storage.filename}: {error}')

            try:
                create_resume(g.supabase, job['id'], parsed['filename'], parsed['raw_text'], parsed['anonymized_text'], status='Analisado')
            except Exception as error:
                app.logger.warning('Falha ao gravar currículo: %s', type(error).__name__)
                abort(503, description='Não foi possível salvar os currículos no banco.')

        return redirect(url_for('vagas', job_id=job['id']))

    return render_template('adicionar_curriculos.html', active_page='candidatos',
                           job=job, jobs=database_jobs(), candidates=candidates)


@app.route('/vagas/<job_id>/candidato/<candidate_id>')
@login_required
def candidato_detalhe(job_id, candidate_id):
    job = database_job(job_id)
    try:
        candidate = get_resume(g.supabase, job['id'], candidate_id)
    except Exception as error:
        app.logger.warning('Falha ao consultar candidato: %s', type(error).__name__)
        abort(503, description='Não foi possível consultar os dados do candidato.')
    if candidate is None:
        abort(404, description='Candidato não encontrado nesta vaga.')
    return render_template('candidato.html', active_page='candidatos', job=job, candidate=candidate)


@app.route('/vagas/<job_id>/candidato/<candidate_id>/status', methods=['POST'])
@login_required
def atualizar_status_candidato(job_id, candidate_id):
    job = database_job(job_id)
    new_status = request.form.get('status')
    try:
        update_resume_status(g.supabase, job['id'], candidate_id, new_status)
    except (ValueError, LookupError) as error:
        abort(400, description=str(error))
    except Exception as error:
        app.logger.warning('Falha ao atualizar status: %s', type(error).__name__)
        abort(503, description='Não foi possível atualizar o status do candidato.')
    return redirect(url_for('candidato_detalhe', job_id=job['id'], candidate_id=candidate_id))
