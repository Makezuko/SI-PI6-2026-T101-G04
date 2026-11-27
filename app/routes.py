import re
from functools import wraps
from typing import Protocol

from flask import abort, flash, g, redirect, render_template, request, session, url_for, jsonify
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

from app.analysis import AnalysisError, attach_analysis, dashboard_scores, ensure_candidate_justification, process_resume
from app import app
from app.repositories import (
    AnalysisSchemaError,
    LegacyProfileError,
    ProfilePersistence,
    SupabaseProfilePersistence,
    create_job,
    create_resume,
    delete_candidate,
    delete_job,
    ensure_profile,
    get_job,
    get_resume,
    list_jobs,
    list_resumes,
    update_job,
    update_resume_status,
)
from app.requisitos import NIVEIS, STATUS_VAGA, TIPOS, build_requirements, rows_from_form
from app.supabase_client import create_supabase_client
from src.data.clean import parse_resume_pdf
from src.matching.telemetry import event, execution_id
from app.auth_diagnostics import stage as auth_stage, failure as auth_failure


@app.context_processor
def requirement_review_helpers():
    from app.requisitos import requirement_warnings
    return {'requirement_warnings': requirement_warnings}


@app.errorhandler(AnalysisSchemaError)
def analysis_schema_error(error):
    return str(error), 503


def remember_tokens(auth_session):
    session['sb_access_token'] = auth_session.access_token
    session['sb_refresh_token'] = auth_session.refresh_token


def finish_login(client, response):
    auth_stage('AUTH_RESPONSE')
    if not response.session:
        raise ValueError('Confirme seu e-mail e faça login.')
    auth_stage('AUTH_VERIFY_USER')
    verified = client.auth.get_user(response.session.access_token).user
    if not verified:
        raise ValueError('Não foi possível verificar a sessão.')
    profile = ensure_profile(client, verified)
    auth_stage('SESSION_CREATE')
    session.clear()
    session['auth_user_id'] = str(verified.id)
    app.session_interface.regenerate(session)
    session.permanent = True
    remember_tokens(response.session)
    session['user_email'] = verified.email
    session['user_name'] = profile.get('nome') or verified.email.split('@')[0]
    session['user_role'] = 'RH'
    session['user_initials'] = ''.join(part[0] for part in session['user_name'].split()[:2]).upper()
    session['user_profile'] = profile
    auth_stage('SESSION_READY')


def _cached_profile_matches(profile, user):
    if not isinstance(profile, dict) or not profile.get('id'):
        return False
    if str(profile.get('auth_user_id') or '') != str(user.id):
        return False
    return (profile.get('email') or '').lower() == (user.email or '').lower()


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
            user = getattr(response, 'user', None) or client.auth.get_user(response.session.access_token).user
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
            use_cached = request.endpoint not in {'configuracoes', 'editar_perfil'}
            cached_profile = session.get('user_profile') if use_cached else None
            if _cached_profile_matches(cached_profile, user):
                g.profile = cached_profile
            else:
                g.profile = ensure_profile(client, user)
                session['user_profile'] = g.profile
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
        auth_stage('CLIENT_CREATE')
        client = create_supabase_client()
        auth_stage('AUTH_SIGN_IN')
        response = client.auth.sign_in_with_password({'email': email, 'password': password})
        finish_login(client, response)
    except AuthApiError as error:
        auth_failure(error)
        return render_template('login.html', error='Não foi possível entrar. Confira as credenciais e a confirmação do e-mail.'), 401
    except LegacyProfileError as error:
        auth_failure(error)
        return render_template('login.html', error='Seu perfil antigo precisa ser vinculado ao Supabase Auth pela equipe.'), 409
    except Exception as error:
        auth_failure(error)
        return render_template('login.html', error=f'Não foi possível concluir o login. Diagnóstico local: {execution_id.get()}.'), 503
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
    scores = dashboard_scores(g.supabase, jobs)
    average = f'{sum(scores) / len(scores):.2f}%' if scores else 'Indisponível'
    return render_template('dashboard.html', active_page='dashboard', jobs=jobs,
                           open_jobs_count=sum(job['status'] == 'Aberta' for job in jobs),
                           total_resumes=total_resumes if total_resumes else '—', avg_match_rate=average)


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
    job = next((item for item in jobs if item['id'] == str(job_id)), None)
    if job is None:
        job = database_job(job_id)
    candidates = attach_analysis(g.supabase, job, list_resumes(g.supabase, job['id']))
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


@app.route('/vagas/<job_id>/excluir', methods=['POST'])
@login_required
def excluir_vaga(job_id):
    job = database_job(job_id)
    try:
        delete_job(g.supabase, job['id'])
    except APIError as error:
        app.logger.warning('Falha Supabase ao excluir vaga: código %s', error.code)
        if error.code == 'PGRST202':
            abort(
                503,
                description='A exclusão ainda não está habilitada no banco. Aplique sql/005_excluir_vagas.sql no Supabase.',
            )
        abort(503, description='O Supabase não conseguiu excluir a vaga e os dados vinculados.')
    except Exception as error:
        app.logger.warning('Falha ao excluir vaga: %s', type(error).__name__)
        abort(503, description='Não foi possível excluir a vaga e os dados vinculados.')
    if job['candidate_count']:
        flash(
            f"Vaga excluída. {job['candidate_count']} currículo(s) e análises vinculados foram removidos.",
            'success',
        )
    else:
        flash('Vaga excluída com sucesso.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/candidatos')
@login_required
def candidatos():
    jobs = database_jobs()
    return redirect(url_for('vagas', job_id=jobs[0]['id'])) if jobs else redirect(url_for('nova_vaga'))


@app.route('/configuracoes')
@login_required
def configuracoes():
    return redirect(url_for('editar_perfil'))


def profile_form(profile, submitted=None):
    form = {
        'name': profile.get('nome') or '',
        'email': profile.get('email') or '',
        'company': profile.get('empresa') or '',
    }
    if submitted is not None:
        form.update({
            'name': submitted.get('name', '').strip(),
            'email': submitted.get('email', '').strip().lower(),
            'company': submitted.get('company', '').strip(),
        })
    return form


def validate_profile_form(form, password, password_confirm):
    if not all(form.values()):
        return 'Preencha nome, e-mail e empresa.'
    if len(form['name']) > 120 or len(form['company']) > 120:
        return 'Nome e empresa devem ter no máximo 120 caracteres.'
    if len(form['email']) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', form['email']):
        return 'Informe um endereço de e-mail válido.'
    if password and password != password_confirm:
        return 'As senhas não coincidem.'
    if password and (len(password) < 8 or len(password) > 128):
        return 'A nova senha deve ter entre 8 e 128 caracteres.'
    return None


def profile_changes(profile, form):
    changes = {}
    if form['name'] != (profile.get('nome') or ''):
        changes['nome'] = form['name']
    if form['company'] != (profile.get('empresa') or ''):
        changes['empresa'] = form['company']
    if form['email'] != (profile.get('email') or '').lower():
        changes['email'] = form['email']
    return changes


def auth_profile_attributes(changes, form, password):
    attributes = {}
    if 'nome' in changes or 'empresa' in changes:
        attributes['data'] = {'name': form['name'], 'company': form['company']}
    if 'email' in changes:
        attributes['email'] = form['email']
    if password:
        attributes['password'] = password
    return attributes


class ProfileAuthWriter(Protocol):
    """Operação mínima exigida do serviço de autenticação."""

    def update_user(self, attributes):
        ...


def update_profile_account(
    auth_writer: ProfileAuthWriter,
    profile_store: ProfilePersistence,
    profile,
    auth_user_id,
    form,
    password,
):
    changes = profile_changes(profile, form)
    attributes = auth_profile_attributes(changes, form, password)

    if attributes:
        response = auth_writer.update_user(attributes)
        if not response.user:
            raise RuntimeError('Supabase não retornou o usuário atualizado.')
        if 'email' in changes:
            changes['email'] = (response.user.email or profile['email']).lower()

    updated_profile = profile
    if changes:
        updated_profile = profile_store.update_profile(
            profile['id'], auth_user_id, changes,
        )
    return updated_profile


def sync_profile_session(updated_profile, submitted_email):
    g.profile = updated_profile
    session['user_profile'] = updated_profile
    session['user_name'] = updated_profile['nome']
    session['user_email'] = updated_profile['email']
    session['user_initials'] = ''.join(
        part[0] for part in updated_profile['nome'].split()[:2]
    ).upper()
    if updated_profile['email'] != submitted_email:
        return 'Perfil atualizado. Confirme o link enviado ao novo e-mail para concluir a alteração.'
    return 'Perfil atualizado com sucesso.'


@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    form = profile_form(g.profile)
    if request.method == 'POST':
        form = profile_form(g.profile, request.form)
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        error = validate_profile_form(form, password, password_confirm)

        if error:
            return render_template('editar_perfil.html', active_page='configuracoes',
                                   form=form, error=error), 400

        try:
            updated_profile = update_profile_account(
                g.supabase.auth,
                SupabaseProfilePersistence(g.supabase),
                g.profile,
                session['auth_user_id'],
                form,
                password,
            )
        except AuthApiError:
            return render_template(
                'editar_perfil.html', active_page='configuracoes', form=form,
                error='Não foi possível atualizar o perfil. Confira o e-mail e os requisitos da nova senha.',
            ), 400
        except LookupError as error:
            app.logger.warning('Perfil não foi atualizado: %s', str(error))
            abort(503, description='Não foi possível confirmar a atualização do perfil. Confira a migração de edição de perfil.')
        except (APIError, RuntimeError) as error:
            app.logger.warning(
                'Falha ao atualizar perfil (%s, código=%s): %s',
                type(error).__name__,
                getattr(error, 'code', None),
                getattr(error, 'message', str(error)),
            )
            abort(503, description='Não foi possível confirmar a atualização do perfil. Reabra a tela antes de tentar novamente.')

        message = sync_profile_session(updated_profile, form['email'])
        flash(message, 'success')
        return redirect(url_for('editar_perfil'))

    return render_template('editar_perfil.html', active_page='configuracoes', form=form, error=None)


@app.route('/vagas/<job_id>/adicionar-curriculos', methods=['GET', 'POST'])
@login_required
def adicionar_curriculos(job_id):
    job = database_job(job_id)
    candidates = attach_analysis(g.supabase, job, list_resumes(g.supabase, job['id']))

    if request.method == 'POST':
        uploaded = request.files.getlist('files')
        valid_files = [f for f in uploaded if f and f.filename and f.filename.strip()]
        selected_ids = set(request.form.getlist('selected_candidates'))

        if not valid_files and not selected_ids:
            abort(400, description='Selecione ao menos um arquivo PDF ou currículo existente.')

        targets = {c['id']: c for c in candidates if c['id'] in selected_ids}
        event('ANALYSIS_TARGETS', selected_count=len(targets))
        for missing in selected_ids - targets.keys():
            flash('Currículo selecionado não encontrado nesta vaga ou sem acesso.', 'error')
        for file_storage in valid_files:
            try:
                if not file_storage.filename.lower().endswith('.pdf'):
                    raise AnalysisError('Envie arquivos no formato PDF.')
                parsed = parse_resume_pdf(file_storage, filename=file_storage.filename)
                resume = create_resume(g.supabase, job['id'], parsed['filename'], parsed['raw_text'], parsed['anonymized_text'])
                targets[resume['id']] = resume
            except AnalysisError as error:
                flash(str(error), 'error')
            except Exception as error:
                app.logger.warning('Falha no upload: %s', type(error).__name__)
                flash('Não foi possível extrair ou salvar um arquivo. Confira o cadastro antes de reenviar.', 'error')
        for resume in targets.values():
            try:
                result = process_resume(g.supabase, job, resume)
                flash(f"Currículo {resume['id']}: análise salva. Execução {execution_id.get()}." if result['score'] is not None else
                      f"Currículo {resume['id']}: análise incompleta salva; sem índice.", 'success')
            except AnalysisError as error:
                flash(f"Currículo {resume['id']}: {error}", 'error')
            except Exception as error:
                from src.matching.telemetry import failure
                failure(error, 'processing')
                flash(f"Falha tecnica no processamento do curriculo {resume['id']} [{type(error).__name__}]. Execucao {execution_id.get()}. Nenhuma nova analise foi salva. Consulte ANALYSIS_STAGE_ERROR no terminal.", 'error')

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
    candidate = attach_analysis(g.supabase, job, [candidate])[0]
    ensure_candidate_justification(g.supabase, job, candidate)
    event('ANALYSIS_SELECTED', found=candidate['analysis'] is not None,
          analysis_id=candidate.get('analysis_id'),
          persisted_run_id=(candidate.get('analysis') or {}).get('execution_id'),
          method='contextual' if (candidate.get('analysis') or {}).get('contextual_configuration') else 'legacy_or_unavailable')
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


@app.route('/vagas/<job_id>/candidato/<candidate_id>/excluir', methods=['POST'])
@login_required
def excluir_candidato(job_id, candidate_id):
    job = database_job(job_id)
    try:
        delete_candidate(g.supabase, job['id'], candidate_id)
    except APIError as error:
        app.logger.warning('Falha Supabase ao excluir candidato: código %s', error.code)
        if error.code == 'PGRST202':
            abort(
                503,
                description='A exclusão de candidatos ainda não está habilitada no banco. Aplique sql/005_excluir_vagas.sql no Supabase.',
            )
        abort(503, description='O Supabase não conseguiu excluir o candidato e sua análise.')
    except (LookupError, ValueError) as error:
        abort(404, description=str(error))
    except Exception as error:
        app.logger.warning('Falha ao excluir candidato: %s', type(error).__name__)
        abort(503, description='Não foi possível excluir o candidato e sua análise.')
    flash('Candidato excluído com sucesso.', 'success')
    return redirect(url_for('vagas', job_id=job['id']))
