import json
import sqlite3

from backend.app.tutoring import recompute
from conftest import space
from test_review import review_action, get_review


def test_majority_state_uses_current_questions_and_latest_unassisted_answers():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE chapters(id TEXT,state TEXT,passed_at TEXT);
        CREATE TABLE questions(id TEXT,chapter_id TEXT,version INTEGER);
        CREATE TABLE attempts(question_id TEXT,disputed INTEGER,created TEXT,feedback TEXT,assisted INTEGER);
        INSERT INTO chapters VALUES('c','已学习，待验证',NULL);
        INSERT INTO questions VALUES('a','c',1),('b','c',1),('d','c',1);
    ''')
    def state():
        recompute(db, 'c')
        return db.execute('SELECT state FROM chapters').fetchone()[0]
    def answer(q, verdict, at='1', assisted=0):
        db.execute('INSERT INTO attempts VALUES(?,0,?,?,?)', (q, at, json.dumps({'verdict': verdict}), assisted))
    assert state() == '已学习，待验证'
    answer('a', 'incorrect')
    assert state() == '需要巩固'
    answer('b', 'correct')
    assert state() == '需要巩固'
    answer('d', 'correct')
    assert state() == '已掌握'  # Two of three, not necessarily all correct.
    answer('d', 'incorrect', '2')
    assert state() == '需要巩固'  # Old successes cannot hide a new mistake.
    answer('d', 'correct', '3', assisted=1)
    assert state() == '需要巩固'
    db.execute("INSERT INTO questions VALUES('new','c',2)")
    assert state() == '已学习，待验证'


def test_invalid_map_gets_one_source_bound_repair(client):
    s = space(client)
    original = client.app.state.provider.generate
    calls = []
    async def generate(kind, context, progress):
        result, usage = await original(kind, context, progress)
        calls.append(context)
        if len(calls) == 1:
            result['nodes'][0]['sources'] = ['wrong-page']
        return result, usage
    client.app.state.provider.generate = generate
    assert review_action(client, s, 'review_map')['status'] == 'done'
    assert len(calls) == 2
    assert 'validation_error' in calls[1]
    assert all('chapter_id' in p for p in calls[0]['evidence'])
    assert get_review(client, s)['map']
