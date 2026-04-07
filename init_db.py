import sqlite3


conn = sqlite3.connect('demandas.db')
cursor = conn.cursor()

cursor.execute('DROP TABLE IF EXISTS comentarios')
cursor.execute('DROP TABLE IF EXISTS demandas')
cursor.execute('DROP TABLE IF EXISTS prioridades')


cursor.execute('''
CREATE TABLE prioridades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    cor TEXT NOT NULL,
    nivel INTEGER NOT NULL UNIQUE,
    data_criacao TEXT NOT NULL
)
''')

cursor.execute("INSERT INTO prioridades (nome, cor, nivel, data_criacao) VALUES ('Alta', '#dc3545', 1, datetime('now'))")
cursor.execute("INSERT INTO prioridades (nome, cor, nivel, data_criacao) VALUES ('Média', '#fd7e14', 2, datetime('now'))")
cursor.execute("INSERT INTO prioridades (nome, cor, nivel, data_criacao) VALUES ('Baixa', '#198754', 3, datetime('now'))")

prioridade_baixa = cursor.execute("SELECT id FROM prioridades WHERE nome = 'Baixa'").fetchone()[0]


cursor.execute('''
CREATE TABLE demandas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descricao TEXT,
    solicitante TEXT,
    data_criacao TEXT NOT NULL,
    prioridade_id INTEGER NOT NULL,
    FOREIGN KEY (prioridade_id) REFERENCES prioridades(id)
)
''')


cursor.execute('''
CREATE TABLE comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demanda_id INTEGER,
    comentario TEXT,
    autor TEXT,
    data TEXT
)
''')


cursor.execute(
    "INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id) VALUES (?, ?, ?, ?, ?)",
    ('Corrigir bug no login', 'Usuários não conseguem fazer login', 'João Silva', '2024-01-15 10:30:00', prioridade_baixa)
)
cursor.execute(
    "INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id) VALUES (?, ?, ?, ?, ?)",
    ('Implementar relatório de vendas', 'Precisamos de um relatório mensal', 'Maria Santos', '2024-01-16 14:20:00', prioridade_baixa)
)
cursor.execute(
    "INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id) VALUES (?, ?, ?, ?, ?)",
    ('Melhorar performance', 'Sistema está lento', 'Pedro Costa', '2024-01-17 09:15:00', prioridade_baixa)
)
cursor.execute(
    "INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade_id) VALUES (?, ?, ?, ?, ?)",
    ('Adicionar filtros', 'Usuários querem filtrar demandas', 'Ana Lima', '2024-01-18 11:00:00', prioridade_baixa)
)

cursor.execute("INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES (1, 'Vou investigar esse bug', 'Tech Team', '2024-01-15 11:00:00')")
cursor.execute("INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES (1, 'Bug corrigido na branch develop', 'Desenvolvedor', '2024-01-15 16:30:00')")

conn.commit()
conn.close()

print("Banco de dados criado com sucesso!")
