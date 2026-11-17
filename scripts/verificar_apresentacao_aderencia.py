"""Visualização offline sintética. Requer Playwright e Chrome local; sem banco."""
from pathlib import Path
import json
from flask import render_template
from app import app
from src.matching.adherence import calculate_adherence


def render_fixture():
    private = 'Pessoa Sintetica'
    evidence = dict(id='e1', source='experience', similarity=.8123,
                    text=(private + ' pessoa@example.test: Modelagem de dados e consultas PostgreSQL.\n') * 22)
    other = dict(id='e2-' + 'a'*180, source='project', text='Projeto sintetico ' + 'B'*400)
    requirements, decisions = [], []
    for i in range(8):
        state = 'atendido' if i < 4 else 'revisao_necessaria' if i < 7 else 'nao_identificado'
        requirements.append(dict(id=f'R{i}', text='Conhecimento em banco de dados relacional e SQL (PostgreSQL)',
                                 nivel='desejavel' if 4 <= i < 7 else 'obrigatorio'))
        decisions.append(dict(id=f'R{i}', estado=state, justificativa='O curriculo descreve modelagem em PostgreSQL.',
                              evidencias=[evidence] if i < 4 else [], diagnostic=dict(
                                  contextual=dict(estado='sustentado' if i < 4 else 'indeterminado',
                                                  evidence_ids=['e1'] if i < 4 else [], base='evidencia', limitacoes=[]),
                                  retrieved_evidence=[evidence, other])))
    analysis = calculate_adherence(requirements, decisions)
    analysis.update(contextual_configuration={}, execution_id='execution-'+'x'*180)
    candidate = dict(id='12', name='Candidato #12', real_name=private, initials='C12', status='Pendente',
                     score=analysis['score'], analysis=analysis, analysis_id='analysis-'+'z'*180,
                     analysis_state='Provisória — revisão necessária', filename='curriculo_12.pdf',
                     submitted_at='17/11/2026', email='Oculto', phone='Oculto', education='Não especificada',
                     last_role='Não identificado', skills=['SQL'], raw_text=private+'\npessoa@example.test',
                     anonymized_text='[NOME OCULTO]\npessoa@example.test')
    job = dict(id='10', title='Backend Python', description='', requirements_data=dict(status='revisado', items=requirements))
    with app.test_request_context('/'):
        html = render_template('candidato.html', job=job, candidate=candidate)
    css = Path('app/static/css/style.css').read_text(encoding='utf-8-sig')
    html = html.replace('<link rel="stylesheet" href="/static/css/style.css">', '<style>'+css+'</style>')
    assert private not in html and 'pessoa@example.test' not in html
    assert '61,54%' in html and 'Há 3 requisitos pendentes de revisão' in html
    return html


def main():
    from playwright.sync_api import sync_playwright
    report = Path('reports/presentation')
    report.mkdir(parents=True, exist_ok=True)
    html = render_fixture()
    (report/'fixture.html').write_text(html, encoding='utf-8')
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        for width in [1280, 390, 320]:
            page = browser.new_page(viewport=dict(width=width, height=900))
            page.route('**/*', lambda route: route.abort())
            page.set_content(html)
            page.screenshot(path=str(report/f'{width}-summary.png'))
            page.locator('.requirement-result').first.scroll_into_view_if_needed()
            page.screenshot(path=str(report/f'{width}-closed.png'))
            page.locator('.evidence-full-link').first.click()
            assert page.locator('.requirement-details').first.get_attribute('open') is not None
            page.locator('details').evaluate_all('(nodes) => nodes.forEach(n => n.open = true)')
            dimensions = page.evaluate('''() => ({viewport: innerWidth, document: document.documentElement.scrollWidth,
              overflowing: [...document.querySelectorAll('.requirement-result, .requirement-evidence, .analysis-technical')]
              .filter(n => n.scrollWidth > n.clientWidth + 1).length})''')
            assert dimensions['document'] <= width, dimensions
            assert dimensions['overflowing'] == 0, dimensions
            assert page.locator('.requirement-details > summary').first.evaluate('(n) => n.tabIndex') == 0
            assert page.locator('.requirement-details').first.inner_text().count('Modelagem de dados') == 22
            page.locator('.requirement-result').first.scroll_into_view_if_needed()
            page.screenshot(path=str(report/f'{width}-open.png'))
            page.screenshot(path=str(report/f'{width}-full.png'), full_page=True)
            results.append(dict(width=width, **dimensions, personal_data_hidden=True))
            page.close()
        browser.close()
    (report/'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
