from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
from unidecode import unidecode
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = '123456'
DATABASE = 'demandas.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.create_function("UNACCENT", 1, lambda x: unidecode(x) if x else "")
    return conn


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Faça login para continuar.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Faça login para continuar.')
            return redirect(url_for('login'))
        if session.get('usuario_tipo') != 'admin':
            flash('Acesso restrito a administradores.')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def get_prioridade_baixa_id(cursor):
    prioridade = cursor.execute(
        "SELECT id FROM prioridades WHERE LOWER(nome) = 'baixa' ORDER BY id LIMIT 1"
    ).fetchone()
    if prioridade:
        return prioridade[0]

    prioridade = cursor.execute(
        'SELECT id FROM prioridades ORDER BY nivel DESC, id DESC LIMIT 1'
    ).fetchone()
    return prioridade[0]


def carregar_usuarios(conn):
    return conn.execute(
        'SELECT id, nome, email, tipo FROM usuarios ORDER BY nome'
    ).fetchall()


def ensure_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('PRAGMA foreign_keys = OFF')

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS prioridades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            cor TEXT NOT NULL,
            nivel INTEGER NOT NULL UNIQUE,
            data_criacao TEXT NOT NULL
        )
        '''
    )

    colunas_prioridades = cursor.execute('PRAGMA table_info(prioridades)').fetchall()
    mapa_colunas_prioridades = {coluna[1]: coluna for coluna in colunas_prioridades}
    if 'data_criacao' not in mapa_colunas_prioridades:
        cursor.execute("ALTER TABLE prioridades ADD COLUMN data_criacao TEXT")
        cursor.execute(
            "UPDATE prioridades SET data_criacao = ? WHERE data_criacao IS NULL OR TRIM(data_criacao) = ''",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),),
        )

    total_prioridades = cursor.execute('SELECT COUNT(*) FROM prioridades').fetchone()[0]
    if total_prioridades == 0:
        cursor.executemany(
            'INSERT INTO prioridades (nome, cor, nivel, data_criacao) VALUES (?, ?, ?, ?)',
            [
                ('Alta', '#dc3545', 1, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                ('Média', '#fd7e14', 2, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                ('Baixa', '#198754', 3, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            ],
        )

    baixa_id = get_prioridade_baixa_id(cursor)

    demanda_table = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='demandas'"
    ).fetchone()

    if not demanda_table:
        cursor.execute(
            '''
            CREATE TABLE demandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descricao TEXT,
                solicitante TEXT,
                data_criacao TEXT NOT NULL,
                prioridade_id INTEGER NOT NULL,
                usuario_id INTEGER,
                FOREIGN KEY (prioridade_id) REFERENCES prioridades(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
            '''
        )
    else:
        colunas = cursor.execute('PRAGMA table_info(demandas)').fetchall()
        mapa_colunas = {coluna[1]: coluna for coluna in colunas}
        precisa_migrar = 'id' not in mapa_colunas or mapa_colunas['id'][5] == 0

        if precisa_migrar:
            cursor.execute('ALTER TABLE demandas RENAME TO demandas_antiga')
            cursor.execute(
                '''
                CREATE TABLE demandas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT NOT NULL,
                    descricao TEXT,
                    solicitante TEXT,
                    data_criacao TEXT NOT NULL,
                    prioridade_id INTEGER NOT NULL,
                    usuario_id INTEGER,
                    FOREIGN KEY (prioridade_id) REFERENCES prioridades(id),
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
                )
                '''
            )

            colunas_antigas = [
                coluna[1]
                for coluna in cursor.execute('PRAGMA table_info(demandas_antiga)').fetchall()
            ]

            titulo_expr = 'titulo' if 'titulo' in colunas_antigas else "''"
            descricao_expr = 'descricao' if 'descricao' in colunas_antigas else 'NULL'
            solicitante_expr = 'solicitante' if 'solicitante' in colunas_antigas else 'NULL'
            data_expr = 'data_criacao' if 'data_criacao' in colunas_antigas else "datetime('now')"

            if 'prioridade_id' in colunas_antigas:
                prioridade_expr = f'COALESCE(prioridade_id, {baixa_id})'
            else:
                prioridade_expr = str(baixa_id)

            cursor.execute(
                f'''
                INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id)
                SELECT {titulo_expr}, {descricao_expr}, {solicitante_expr}, {data_expr}, {prioridade_expr}
                FROM demandas_antiga
                '''
            )
            cursor.execute('DROP TABLE demandas_antiga')
        else:
            if 'prioridade_id' not in mapa_colunas:
                cursor.execute(f'ALTER TABLE demandas ADD COLUMN prioridade_id INTEGER DEFAULT {baixa_id}')
                cursor.execute('UPDATE demandas SET prioridade_id = ? WHERE prioridade_id IS NULL', (baixa_id,))

            if 'usuario_id' not in mapa_colunas:
                cursor.execute('ALTER TABLE demandas ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)')

    comentarios_table = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='comentarios'"
    ).fetchone()

    if not comentarios_table:
        cursor.execute(
            '''
            CREATE TABLE comentarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_id INTEGER,
                comentario TEXT,
                autor TEXT,
                data TEXT
            )
            '''
        )
    else:
        colunas_comentarios = cursor.execute('PRAGMA table_info(comentarios)').fetchall()
        id_info = next((coluna for coluna in colunas_comentarios if coluna[1] == 'id'), None)
        if not id_info or id_info[5] == 0:
            cursor.execute('ALTER TABLE comentarios RENAME TO comentarios_antigos')
            cursor.execute(
                '''
                CREATE TABLE comentarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    demanda_id INTEGER,
                    comentario TEXT,
                    autor TEXT,
                    data TEXT
                )
                '''
            )

            colunas_antigas = [
                coluna[1]
                for coluna in cursor.execute('PRAGMA table_info(comentarios_antigos)').fetchall()
            ]
            demanda_expr = 'demanda_id' if 'demanda_id' in colunas_antigas else 'NULL'
            comentario_expr = 'comentario' if 'comentario' in colunas_antigas else "''"
            autor_expr = 'autor' if 'autor' in colunas_antigas else "''"
            data_expr = 'data' if 'data' in colunas_antigas else "datetime('now')"

            cursor.execute(
                f'''
                INSERT INTO comentarios (demanda_id, comentario, autor, data)
                SELECT {demanda_expr}, {comentario_expr}, {autor_expr}, {data_expr}
                FROM comentarios_antigos
                '''
            )
            cursor.execute('DROP TABLE comentarios_antigos')

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'solicitante',
            data_criacao TEXT NOT NULL
        )
        '''
    )

    admin_exists = cursor.execute(
        "SELECT COUNT(*) FROM usuarios WHERE email = 'admin@admin.com'"
    ).fetchone()[0]
    if not admin_exists:
        cursor.execute(
            'INSERT INTO usuarios (nome, email, senha_hash, tipo, data_criacao) VALUES (?, ?, ?, ?, ?)',
            (
                'Administrador',
                'admin@admin.com',
                generate_password_hash('admin123'),
                'admin',
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ),
        )

    cursor.execute('PRAGMA foreign_keys = ON')
    conn.commit()
    conn.close()


def carregar_prioridades(conn):
    return conn.execute('SELECT * FROM prioridades ORDER BY nivel ASC, data_criacao ASC').fetchall()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        conn = get_db()
        usuario = conn.execute(
            'SELECT * FROM usuarios WHERE email = ?', (email,)
        ).fetchone()
        conn.close()

        if usuario and check_password_hash(usuario['senha_hash'], senha):
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            session['usuario_tipo'] = usuario['tipo']
            return redirect(url_for('index'))

        flash('Email ou senha inválidos.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    conn = get_db()
    prioridades = carregar_prioridades(conn)
    usuarios = carregar_usuarios(conn)

    prioridade_id = request.args.get('prioridade_id', '').strip()
    solicitante_id = request.args.get('solicitante_id', '').strip()
    ordem = request.args.get('ordem', 'prioridade_maior').strip()

    ordens_validas = {
        'prioridade_maior': 'p.nivel ASC, d.data_criacao ASC',
        'prioridade_menor': 'p.nivel DESC, d.data_criacao ASC',
        'data_desc': 'd.data_criacao DESC',
        'data_asc': 'd.data_criacao ASC',
        'titulo': 'd.titulo ASC',
    }
    order_clause = ordens_validas.get(ordem, 'p.nivel ASC, d.data_criacao ASC')

    is_admin = session.get('usuario_tipo') == 'admin'
    usuario_id = session.get('usuario_id')

    conditions = []
    params = []

    if not is_admin:
        conditions.append('d.usuario_id = ?')
        params.append(usuario_id)

    if prioridade_id:
        conditions.append('d.prioridade_id = ?')
        params.append(prioridade_id)

    if solicitante_id:
        conditions.append('d.usuario_id = ?')
        params.append(solicitante_id)

    where_clause = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    demandas = conn.execute(
        f'''
        SELECT d.*, p.nome AS prioridade_nome, p.cor AS prioridade_cor, p.nivel AS prioridade_nivel
        FROM demandas d
        JOIN prioridades p ON p.id = d.prioridade_id
        {where_clause}
        ORDER BY {order_clause}
        ''',
        params,
    ).fetchall()

    conn.close()
    return render_template(
        'index.html',
        demandas=demandas,
        prioridades=prioridades,
        usuarios=usuarios,
        prioridade_filtro=prioridade_id,
        solicitante_filtro=solicitante_id,
        ordem=ordem,
    )


@app.route('/relatorios')
@admin_required
def relatorios():
    conn = get_db()
    usuarios = carregar_usuarios(conn)
    data_minima = '1900-01-01'
    data_maxima = datetime.now().strftime('%Y-%m-%d')

    solicitante_id = request.args.get('solicitante_id', '').strip()
    data_inicial = request.args.get('data_inicial', '').strip()
    data_final = request.args.get('data_final', '').strip()

    if not solicitante_id and not data_inicial and not data_final:
        conn.close()
        return render_template(
            'relatorios.html',
            usuarios=usuarios,
            demandas=[],
            solicitante_filtro='',
            data_inicial='',
            data_final='',
            data_minima=data_minima,
            data_maxima=data_maxima,
            relatorio_pronto=False,
        )

    if not solicitante_id or not data_inicial or not data_final:
        flash('Solicitante, data inicial e data final são obrigatórios.')
        conn.close()
        return render_template(
            'relatorios.html',
            usuarios=usuarios,
            demandas=[],
            solicitante_filtro=solicitante_id,
            data_inicial=data_inicial,
            data_final=data_final,
            data_minima=data_minima,
            data_maxima=data_maxima,
            relatorio_pronto=False,
        )

    try:
        data_inicial_obj = datetime.strptime(data_inicial, '%Y-%m-%d').date()
        data_final_obj = datetime.strptime(data_final, '%Y-%m-%d').date()
        data_minima_obj = datetime.strptime(data_minima, '%Y-%m-%d').date()
        data_maxima_obj = datetime.strptime(data_maxima, '%Y-%m-%d').date()
    except ValueError:
        flash('Informe datas válidas no formato correto.')
        conn.close()
        return render_template(
            'relatorios.html',
            usuarios=usuarios,
            demandas=[],
            solicitante_filtro=solicitante_id,
            data_inicial=data_inicial,
            data_final=data_final,
            data_minima=data_minima,
            data_maxima=data_maxima,
            relatorio_pronto=False,
        )

    if data_inicial_obj < data_minima_obj or data_final_obj < data_minima_obj:
        flash('As datas devem ser a partir de 1900-01-01.')
        conn.close()
        return render_template(
            'relatorios.html',
            usuarios=usuarios,
            demandas=[],
            solicitante_filtro=solicitante_id,
            data_inicial=data_inicial,
            data_final=data_final,
            data_minima=data_minima,
            data_maxima=data_maxima,
            relatorio_pronto=False,
        )

    if data_inicial_obj > data_maxima_obj or data_final_obj > data_maxima_obj:
        flash('As datas não podem ser maiores que a data atual.')
        conn.close()
        return render_template(
            'relatorios.html',
            usuarios=usuarios,
            demandas=[],
            solicitante_filtro=solicitante_id,
            data_inicial=data_inicial,
            data_final=data_final,
            data_minima=data_minima,
            data_maxima=data_maxima,
            relatorio_pronto=False,
        )

    if data_inicial_obj > data_final_obj:
        flash('A data inicial não pode ser maior que a data final.')
        conn.close()
        return render_template(
            'relatorios.html',
            usuarios=usuarios,
            demandas=[],
            solicitante_filtro=solicitante_id,
            data_inicial=data_inicial,
            data_final=data_final,
            data_minima=data_minima,
            data_maxima=data_maxima,
            relatorio_pronto=False,
        )

    conditions = []
    params = []

    if solicitante_id:
        conditions.append('d.usuario_id = ?')
        params.append(solicitante_id)

    if data_inicial:
        conditions.append('date(d.data_criacao) >= date(?)')
        params.append(data_inicial)

    if data_final:
        conditions.append('date(d.data_criacao) <= date(?)')
        params.append(data_final)

    where_clause = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    demandas = conn.execute(
        f'''
        SELECT
            d.*,
            p.nome AS prioridade_nome,
            p.cor AS prioridade_cor,
            p.nivel AS prioridade_nivel,
            u.nome AS usuario_nome,
            u.email AS usuario_email
        FROM demandas d
        JOIN prioridades p ON p.id = d.prioridade_id
        LEFT JOIN usuarios u ON u.id = d.usuario_id
        {where_clause}
        ORDER BY d.data_criacao DESC, p.nivel ASC
        ''',
        params,
    ).fetchall()

    conn.close()
    return render_template(
        'relatorios.html',
        usuarios=usuarios,
        demandas=demandas,
        solicitante_filtro=solicitante_id,
        data_inicial=data_inicial,
        data_final=data_final,
        data_minima=data_minima,
        data_maxima=data_maxima,
        relatorio_pronto=True,
    )


@app.route('/nova_demanda', methods=['GET', 'POST'])
@login_required
def nova_demanda():
    conn = get_db()
    prioridades = carregar_prioridades(conn)
    is_admin = session.get('usuario_tipo') == 'admin'
    usuarios = carregar_usuarios(conn) if is_admin else []

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        descricao = request.form.get('descricao', '').strip()
        prioridade_id = request.form.get('prioridade_id', '').strip()

        if is_admin:
            usuario_id_demanda = request.form.get('usuario_id', '').strip()
            usuario = None
            if usuario_id_demanda:
                usuario = conn.execute(
                    'SELECT id, nome FROM usuarios WHERE id = ?',
                    (usuario_id_demanda,),
                ).fetchone()

            if not usuario:
                flash('Solicitante é obrigatório.')
                conn.close()
                return render_template(
                    'nova_demanda.html',
                    prioridades=prioridades,
                    is_admin=is_admin,
                    usuarios=usuarios,
                )

            solicitante = usuario['nome']
            usuario_id_demanda = usuario['id']
        else:
            solicitante = session.get('usuario_nome', '')
            usuario_id_demanda = session.get('usuario_id')

        if not titulo:
            flash('Título é obrigatório.')
            conn.close()
            return render_template(
                'nova_demanda.html',
                prioridades=prioridades,
                is_admin=is_admin,
                usuarios=usuarios,
            )

        if not prioridade_id:
            flash('Prioridade é obrigatória.')
            conn.close()
            return render_template(
                'nova_demanda.html',
                prioridades=prioridades,
                is_admin=is_admin,
                usuarios=usuarios,
            )

        conn.execute(
            '''
            INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (titulo, descricao, solicitante, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), prioridade_id, usuario_id_demanda),
        )
        conn.commit()
        conn.close()

        flash('Salvo!')
        return redirect(url_for('index'))

    conn.close()
    return render_template(
        'nova_demanda.html',
        prioridades=prioridades,
        is_admin=is_admin,
        usuarios=usuarios,
    )


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    conn = get_db()
    demanda = conn.execute('SELECT * FROM demandas WHERE id = ?', (id,)).fetchone()
    if not demanda:
        conn.close()
        flash('Demanda não encontrada.')
        return redirect(url_for('index'))

    is_admin = session.get('usuario_tipo') == 'admin'

    if not is_admin and demanda['usuario_id'] != session.get('usuario_id'):
        conn.close()
        flash('Sem permissão para editar esta demanda.')
        return redirect(url_for('index'))

    prioridades = carregar_prioridades(conn)
    usuarios = carregar_usuarios(conn) if is_admin else []

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        descricao = request.form.get('descricao', '').strip()
        prioridade_id = request.form.get('prioridade_id', '').strip()

        if is_admin:
            usuario_id_demanda = request.form.get('usuario_id', '').strip()
            usuario = None
            if usuario_id_demanda:
                usuario = conn.execute(
                    'SELECT id, nome FROM usuarios WHERE id = ?',
                    (usuario_id_demanda,),
                ).fetchone()

            if not usuario:
                flash('Solicitante é obrigatório.')
                conn.close()
                return render_template(
                    'editar.html',
                    demanda=demanda,
                    prioridades=prioridades,
                    is_admin=is_admin,
                    usuarios=usuarios,
                )

            solicitante = usuario['nome']
            usuario_id_demanda = usuario['id']
        else:
            solicitante = demanda['solicitante']
            usuario_id_demanda = demanda['usuario_id']

        if not titulo:
            flash('Título é obrigatório.')
            conn.close()
            return render_template(
                'editar.html',
                demanda=demanda,
                prioridades=prioridades,
                is_admin=is_admin,
                usuarios=usuarios,
            )

        if not prioridade_id:
            flash('Prioridade é obrigatória.')
            conn.close()
            return render_template(
                'editar.html',
                demanda=demanda,
                prioridades=prioridades,
                is_admin=is_admin,
                usuarios=usuarios,
            )

        conn.execute(
            '''
            UPDATE demandas
            SET titulo = ?, descricao = ?, solicitante = ?, prioridade_id = ?, usuario_id = ?
            WHERE id = ?
            ''',
            (titulo, descricao, solicitante, prioridade_id, usuario_id_demanda, id),
        )
        conn.commit()
        conn.close()
        flash('Atualizado!')
        return redirect(url_for('index'))

    conn.close()
    return render_template(
        'editar.html',
        demanda=demanda,
        prioridades=prioridades,
        is_admin=is_admin,
        usuarios=usuarios,
    )


@app.route('/deletar/<int:id>')
@admin_required
def deletar(id):
    conn = get_db()
    conn.execute('DELETE FROM demandas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Deletado!')
    return redirect(url_for('index'))


@app.route('/buscar')
@login_required
def buscar():
    termo = request.args.get('q', '').strip()
    termo_like = f"%{termo}%"

    conn = get_db()
    prioridades = carregar_prioridades(conn)
    is_admin = session.get('usuario_tipo') == 'admin'
    usuario_id = session.get('usuario_id')

    if is_admin:
        resultados = conn.execute(
            '''
            SELECT d.*, p.nome AS prioridade_nome, p.cor AS prioridade_cor, p.nivel AS prioridade_nivel
            FROM demandas d
            JOIN prioridades p ON p.id = d.prioridade_id
            WHERE
                UNACCENT(lower(d.titulo)) LIKE UNACCENT(lower(?))
                OR UNACCENT(lower(p.nome)) LIKE UNACCENT(lower(?))
            ORDER BY p.nivel ASC, d.data_criacao DESC
            ''',
            (termo_like, termo_like),
        ).fetchall()
    else:
        resultados = conn.execute(
            '''
            SELECT d.*, p.nome AS prioridade_nome, p.cor AS prioridade_cor, p.nivel AS prioridade_nivel
            FROM demandas d
            JOIN prioridades p ON p.id = d.prioridade_id
            WHERE
                d.usuario_id = ?
                AND (
                    UNACCENT(lower(d.titulo)) LIKE UNACCENT(lower(?))
                    OR UNACCENT(lower(p.nome)) LIKE UNACCENT(lower(?))
                )
            ORDER BY p.nivel ASC, d.data_criacao DESC
            ''',
            (usuario_id, termo_like, termo_like),
        ).fetchall()

    conn.close()
    return render_template('index.html', demandas=resultados, prioridades=prioridades, prioridade_filtro='', ordem='prioridade_maior')


@app.route('/prioridades')
@admin_required
def prioridades():
    conn = get_db()
    lista = carregar_prioridades(conn)
    conn.close()
    return render_template('prioridades.html', prioridades=lista)


@app.route('/prioridades/nova', methods=['POST'])
@admin_required
def nova_prioridade():
    nome = request.form.get('nome', '').strip()
    cor = request.form.get('cor', '').strip()
    nivel = request.form.get('nivel', '').strip()

    if not nome or not cor or not nivel:
        flash('Nome, cor e ordem da prioridade são obrigatórios.')
        return redirect(url_for('prioridades'))

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO prioridades (nome, cor, nivel, data_criacao) VALUES (?, ?, ?, ?)',
            (nome, cor, int(nivel), datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        )
        conn.commit()
        flash('Prioridade criada!')
    except ValueError:
        flash('A ordem de prioridade deve ser um número inteiro.')
    except sqlite3.IntegrityError:
        flash('Nome ou ordem de prioridade já existem.')
    finally:
        conn.close()

    return redirect(url_for('prioridades'))


@app.route('/prioridades/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_prioridade(id):
    conn = get_db()
    prioridade = conn.execute('SELECT * FROM prioridades WHERE id = ?', (id,)).fetchone()
    if not prioridade:
        conn.close()
        flash('Prioridade não encontrada.')
        return redirect(url_for('prioridades'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cor = request.form.get('cor', '').strip()
        nivel = request.form.get('nivel', '').strip()

        if not nome or not cor or not nivel:
            conn.close()
            flash('Nome, cor e ordem da prioridade são obrigatórios.')
            return redirect(url_for('editar_prioridade', id=id))

        try:
            conn.execute(
                'UPDATE prioridades SET nome = ?, cor = ?, nivel = ? WHERE id = ?',
                (nome, cor, int(nivel), id),
            )
            conn.commit()
            conn.close()
            flash('Prioridade atualizada!')
            return redirect(url_for('prioridades'))
        except ValueError:
            flash('A ordem de prioridade deve ser um número inteiro.')
        except sqlite3.IntegrityError:
            flash('Nome ou ordem de prioridade já existem.')

    conn.close()
    return render_template('editar_prioridade.html', prioridade=prioridade)


@app.route('/prioridades/excluir/<int:id>')
@admin_required
def excluir_prioridade(id):
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM prioridades').fetchone()[0]
    if total <= 3:
        conn.close()
        flash('É necessário manter pelo menos 3 níveis de prioridade.')
        return redirect(url_for('prioridades'))

    uso = conn.execute('SELECT COUNT(*) FROM demandas WHERE prioridade_id = ?', (id,)).fetchone()[0]
    if uso > 0:
        conn.close()
        flash('Não é possível excluir uma prioridade já utilizada em demandas.')
        return redirect(url_for('prioridades'))

    conn.execute('DELETE FROM prioridades WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Prioridade excluída!')
    return redirect(url_for('prioridades'))


@app.route('/detalhes/<int:id>')
@login_required
def detalhes(id):
    conn = get_db()
    demanda = conn.execute(
        '''
        SELECT d.*, p.nome AS prioridade_nome, p.cor AS prioridade_cor, p.nivel AS prioridade_nivel
        FROM demandas d
        JOIN prioridades p ON p.id = d.prioridade_id
        WHERE d.id = ?
        ''',
        (id,),
    ).fetchone()

    if not demanda:
        conn.close()
        flash('Demanda não encontrada.')
        return redirect(url_for('index'))

    is_admin = session.get('usuario_tipo') == 'admin'

    if not is_admin and demanda['usuario_id'] != session.get('usuario_id'):
        conn.close()
        flash('Sem permissão para ver esta demanda.')
        return redirect(url_for('index'))

    comentarios = conn.execute(
        'SELECT * FROM comentarios WHERE demanda_id = ? ORDER BY data DESC',
        (id,),
    ).fetchall()
    conn.close()

    return render_template('detalhes.html', demanda=demanda, comentarios=comentarios, is_admin=is_admin)


@app.route('/adicionar_comentario/<int:demanda_id>', methods=['POST'])
@login_required
def adicionar_comentario(demanda_id):
    comentario = request.form.get('comentario', '').strip()

    if not comentario:
        flash('Comentário é obrigatório.')
        return redirect(url_for('detalhes', id=demanda_id))

    is_admin = session.get('usuario_tipo') == 'admin'

    if not is_admin:
        conn = get_db()
        demanda = conn.execute('SELECT usuario_id FROM demandas WHERE id = ?', (demanda_id,)).fetchone()
        conn.close()
        if not demanda or demanda['usuario_id'] != session.get('usuario_id'):
            flash('Sem permissão para comentar nesta demanda.')
            return redirect(url_for('index'))

    autor = session.get('usuario_nome', '')

    conn = get_db()
    conn.execute(
        'INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES (?, ?, ?, ?)',
        (demanda_id, comentario, autor, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    )
    conn.commit()
    conn.close()

    return redirect(url_for('detalhes', id=demanda_id))


@app.route('/usuarios')
@admin_required
def usuarios():
    conn = get_db()
    lista = conn.execute(
        'SELECT id, nome, email, tipo, data_criacao FROM usuarios ORDER BY nome'
    ).fetchall()
    conn.close()
    return render_template('usuarios.html', usuarios=lista)


@app.route('/usuarios/novo', methods=['GET', 'POST'])
@admin_required
def novo_usuario():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        tipo = request.form.get('tipo', 'solicitante').strip()

        if not nome or not email or not senha:
            flash('Nome, email e senha são obrigatórios.')
            return render_template('novo_usuario.html')

        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO usuarios (nome, email, senha_hash, tipo, data_criacao) VALUES (?, ?, ?, ?, ?)',
                (
                    nome,
                    email,
                    generate_password_hash(senha),
                    tipo if tipo in ('admin', 'solicitante') else 'solicitante',
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ),
            )
            conn.commit()
            flash('Usuário criado com sucesso!')
            return redirect(url_for('usuarios'))
        except sqlite3.IntegrityError:
            flash('Este email já está cadastrado.')
        finally:
            conn.close()

    return render_template('novo_usuario.html')


@app.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_usuario(id):
    conn = get_db()
    usuario = conn.execute(
        'SELECT id, nome, email, tipo, data_criacao FROM usuarios WHERE id = ?',
        (id,),
    ).fetchone()

    if not usuario:
        conn.close()
        flash('Usuário não encontrado.')
        return redirect(url_for('usuarios'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        tipo = request.form.get('tipo', 'solicitante').strip()

        if not nome or not email:
            conn.close()
            flash('Nome e email são obrigatórios.')
            return render_template('editar_usuario.html', usuario=usuario)

        if tipo not in ('admin', 'solicitante'):
            tipo = 'solicitante'

        try:
            if senha:
                conn.execute(
                    'UPDATE usuarios SET nome = ?, email = ?, senha_hash = ?, tipo = ? WHERE id = ?',
                    (nome, email, generate_password_hash(senha), tipo, id),
                )
            else:
                conn.execute(
                    'UPDATE usuarios SET nome = ?, email = ?, tipo = ? WHERE id = ?',
                    (nome, email, tipo, id),
                )

            conn.commit()

            if session.get('usuario_id') == id:
                session['usuario_nome'] = nome
                session['usuario_tipo'] = tipo

            conn.close()
            flash('Usuário atualizado com sucesso!')
            return redirect(url_for('usuarios'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('Este email já está cadastrado.')
            usuario_data = {
                'id': id,
                'nome': nome,
                'email': email,
                'tipo': tipo,
                'data_criacao': usuario['data_criacao'],
            }
            return render_template('editar_usuario.html', usuario=usuario_data)

    conn.close()
    return render_template('editar_usuario.html', usuario=usuario)


@app.route('/usuarios/excluir/<int:id>', methods=['POST'])
@admin_required
def excluir_usuario(id):
    conn = get_db()
    usuario = conn.execute(
        'SELECT id, nome, tipo FROM usuarios WHERE id = ?',
        (id,),
    ).fetchone()

    if not usuario:
        conn.close()
        flash('Usuário não encontrado.')
        return redirect(url_for('usuarios'))

    if session.get('usuario_id') == id:
        conn.close()
        flash('Não é possível excluir o próprio usuário logado.')
        return redirect(url_for('usuarios'))

    demandas_vinculadas = conn.execute(
        'SELECT COUNT(*) FROM demandas WHERE usuario_id = ?',
        (id,),
    ).fetchone()[0]

    if demandas_vinculadas > 0:
        conn.close()
        flash('Não é possível excluir um usuário vinculado a demandas.')
        return redirect(url_for('usuarios'))

    total_admins = conn.execute(
        "SELECT COUNT(*) FROM usuarios WHERE tipo = 'admin'"
    ).fetchone()[0]

    if usuario['tipo'] == 'admin' and total_admins <= 1:
        conn.close()
        flash('É necessário manter pelo menos um usuário administrador.')
        return redirect(url_for('usuarios'))

    conn.execute('DELETE FROM usuarios WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Usuário excluído com sucesso!')
    return redirect(url_for('usuarios'))


def calcular_prazo(data_inicio):
    return '30 dias'


ensure_database()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
