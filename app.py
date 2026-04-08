from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
from unidecode import unidecode

app = Flask(__name__)
app.secret_key = '123456'
DATABASE = 'demandas.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.create_function("UNACCENT", 1, lambda x: unidecode(x) if x else "")
    return conn


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
                FOREIGN KEY (prioridade_id) REFERENCES prioridades(id)
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
                    FOREIGN KEY (prioridade_id) REFERENCES prioridades(id)
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
        elif 'prioridade_id' not in mapa_colunas:
            cursor.execute(f'ALTER TABLE demandas ADD COLUMN prioridade_id INTEGER DEFAULT {baixa_id}')
            cursor.execute('UPDATE demandas SET prioridade_id = ? WHERE prioridade_id IS NULL', (baixa_id,))

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

    cursor.execute('PRAGMA foreign_keys = ON')
    conn.commit()
    conn.close()


def carregar_prioridades(conn):
    return conn.execute('SELECT * FROM prioridades ORDER BY nivel ASC, data_criacao ASC').fetchall()


@app.route('/')
def index():
    conn = get_db()
    prioridades = carregar_prioridades(conn)

    prioridade_id = request.args.get('prioridade_id', '').strip()
    ordem = request.args.get('ordem', 'prioridade_maior').strip()

    ordens_validas = {
        'prioridade_maior': 'p.nivel ASC, d.data_criacao ASC',
        'prioridade_menor': 'p.nivel DESC, d.data_criacao ASC',
        'data_desc':        'd.data_criacao DESC',
        'data_asc':         'd.data_criacao ASC',
        'titulo':           'd.titulo ASC',
    }
    order_clause = ordens_validas.get(ordem, 'p.nivel ASC, d.data_criacao ASC')

    if prioridade_id:
        demandas = conn.execute(
            '''
            SELECT d.*, p.nome AS prioridade_nome, p.cor AS prioridade_cor, p.nivel AS prioridade_nivel
            FROM demandas d
            JOIN prioridades p ON p.id = d.prioridade_id
            WHERE d.prioridade_id = ?
            ORDER BY {}
            '''.format(order_clause),
            (prioridade_id,),
        ).fetchall()
    else:
        demandas = conn.execute(
            '''
            SELECT d.*, p.nome AS prioridade_nome, p.cor AS prioridade_cor, p.nivel AS prioridade_nivel
            FROM demandas d
            JOIN prioridades p ON p.id = d.prioridade_id
            ORDER BY {}
            '''.format(order_clause),
        ).fetchall()

    conn.close()
    return render_template(
        'index.html',
        demandas=demandas,
        prioridades=prioridades,
        prioridade_filtro=prioridade_id,
        ordem=ordem,
    )


@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    conn = get_db()
    prioridades = carregar_prioridades(conn)

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        descricao = request.form.get('descricao', '').strip()
        solicitante = request.form.get('solicitante', '').strip()
        prioridade_id = request.form.get('prioridade_id', '').strip()

        if not titulo:
            flash('Título é obrigatório.')
            conn.close()
            return render_template('nova_demanda.html', prioridades=prioridades)

        if not prioridade_id:
            flash('Prioridade é obrigatória.')
            conn.close()
            return render_template('nova_demanda.html', prioridades=prioridades)

        conn.execute(
            '''
            INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (titulo, descricao, solicitante, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), prioridade_id),
        )
        conn.commit()
        conn.close()

        flash('Salvo!')
        return redirect(url_for('index'))

    conn.close()
    return render_template('nova_demanda.html', prioridades=prioridades)


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    conn = get_db()
    demanda = conn.execute('SELECT * FROM demandas WHERE id = ?', (id,)).fetchone()
    if not demanda:
        conn.close()
        flash('Demanda não encontrada.')
        return redirect(url_for('index'))

    prioridades = carregar_prioridades(conn)

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        descricao = request.form.get('descricao', '').strip()
        solicitante = request.form.get('solicitante', '').strip()
        prioridade_id = request.form.get('prioridade_id', '').strip()

        if not titulo:
            flash('Título é obrigatório.')
            conn.close()
            return render_template('editar.html', demanda=demanda, prioridades=prioridades)

        if not prioridade_id:
            flash('Prioridade é obrigatória.')
            conn.close()
            return render_template('editar.html', demanda=demanda, prioridades=prioridades)

        conn.execute(
            '''
            UPDATE demandas
            SET titulo = ?, descricao = ?, solicitante = ?, prioridade_id = ?
            WHERE id = ?
            ''',
            (titulo, descricao, solicitante, prioridade_id, id),
        )
        conn.commit()
        conn.close()
        flash('Atualizado!')
        return redirect(url_for('index'))

    conn.close()
    return render_template('editar.html', demanda=demanda, prioridades=prioridades)


@app.route('/deletar/<int:id>')
def deletar(id):
    conn = get_db()
    conn.execute('DELETE FROM demandas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Deletado!')
    return redirect(url_for('index'))


@app.route('/buscar')
def buscar():
    termo = request.args.get('q', '').strip().lower()
    termo = f"%{termo}%"

    conn = get_db()

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
        (termo, termo),
    ).fetchall()

    conn.close()
    return render_template('index.html', demandas=resultados)


@app.route('/prioridades')
def prioridades():
    conn = get_db()
    lista = carregar_prioridades(conn)
    conn.close()
    return render_template('prioridades.html', prioridades=lista)


@app.route('/prioridades/nova', methods=['POST'])
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

    comentarios = conn.execute(
        'SELECT * FROM comentarios WHERE demanda_id = ? ORDER BY data DESC',
        (id,),
    ).fetchall()
    conn.close()

    return render_template('detalhes.html', demanda=demanda, comentarios=comentarios)


@app.route('/adicionar_comentario/<int:demanda_id>', methods=['POST'])
def adicionar_comentario(demanda_id):
    comentario = request.form.get('comentario', '').strip()
    autor = request.form.get('autor', '').strip()

    if not comentario or not autor:
        flash('Autor e comentário são obrigatórios.')
        return redirect(url_for('detalhes', id=demanda_id))

    conn = get_db()
    conn.execute(
        'INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES (?, ?, ?, ?)',
        (demanda_id, comentario, autor, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    )
    conn.commit()
    conn.close()

    return redirect(url_for('detalhes', id=demanda_id))


def calcular_prazo(data_inicio):
    return '30 dias'


ensure_database()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')