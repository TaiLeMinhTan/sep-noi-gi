import json
import sqlite3
from flask import current_app, g

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  onboarding_done INTEGER DEFAULT 0,
  role TEXT NOT NULL DEFAULT 'user',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS profiles(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL,
  age INTEGER,
  occupation TEXT,
  industry TEXT,
  english_level TEXT,
  goals TEXT,
  situations TEXT,
  preferred_accent TEXT DEFAULT 'en-US',
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS sentences(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  original_text TEXT NOT NULL,
  normalized_text TEXT UNIQUE NOT NULL,
  context_category TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS lessons(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sentence_id INTEGER NOT NULL,
  context_key TEXT NOT NULL DEFAULT 'general',
  ai_model TEXT DEFAULT 'seed-v1.2',
  lesson_json TEXT NOT NULL,
  image_prompt TEXT,
  image_path TEXT,
  source TEXT DEFAULT 'seed',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(sentence_id,context_key),
  FOREIGN KEY(sentence_id) REFERENCES sentences(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS visual_assets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_id INTEGER UNIQUE NOT NULL,
  visual_key TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  image_model TEXT,
  vision_model TEXT,
  prompt TEXT,
  image_path TEXT,
  match_score INTEGER,
  qa_json TEXT,
  accepted_attempt INTEGER,
  generation_count INTEGER DEFAULT 0,
  total_tokens INTEGER DEFAULT 0,
  last_error TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS visual_attempts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  visual_asset_id INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  generation_response_id TEXT,
  generation_tokens INTEGER,
  qa_response_id TEXT,
  qa_tokens INTEGER,
  match_score INTEGER,
  accepted INTEGER DEFAULT 0,
  qa_json TEXT,
  error_message TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(visual_asset_id) REFERENCES visual_assets(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS patterns(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern TEXT UNIQUE NOT NULL,
  description TEXT,
  example_json TEXT,
  frequency INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sentence_patterns(
  sentence_id INTEGER,
  pattern_id INTEGER,
  PRIMARY KEY(sentence_id,pattern_id),
  FOREIGN KEY(sentence_id) REFERENCES sentences(id) ON DELETE CASCADE,
  FOREIGN KEY(pattern_id) REFERENCES patterns(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS user_learning(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  lesson_id INTEGER NOT NULL,
  status TEXT DEFAULT 'new',
  first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  mastery_score REAL DEFAULT 0,
  favorite INTEGER DEFAULT 0,
  UNIQUE(user_id,lesson_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS daily_learning(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  lesson_id INTEGER NOT NULL,
  activity_date TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, lesson_id, activity_date),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_daily_learning_user_date
ON daily_learning(user_id, activity_date);

CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  lesson_id INTEGER NOT NULL,
  result TEXT,
  reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  next_review_at DATETIME,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ai_requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  sentence_text TEXT NOT NULL,
  context_key TEXT NOT NULL,
  status TEXT NOT NULL,
  cache_hit INTEGER DEFAULT 0,
  ai_model TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  total_tokens INTEGER,
  response_id TEXT,
  error_message TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_lessons_context ON lessons(context_key);
CREATE INDEX IF NOT EXISTS idx_visual_status ON visual_assets(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_visual_attempts_asset ON visual_attempts(visual_asset_id,attempt_no);
CREATE INDEX IF NOT EXISTS idx_ai_requests_user ON ai_requests(user_id,created_at);
CREATE TABLE IF NOT EXISTS api_usage_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  event_type TEXT NOT NULL,
  model TEXT NOT NULL,
  lesson_id INTEGER,
  visual_asset_id INTEGER,
  request_id TEXT,
  input_tokens INTEGER DEFAULT 0,
  cached_input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  image_input_tokens INTEGER DEFAULT 0,
  image_output_tokens INTEGER DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  pricing_snapshot_json TEXT NOT NULL,
  metadata_json TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
  FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE SET NULL,
  FOREIGN KEY(visual_asset_id) REFERENCES visual_assets(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON api_usage_events(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user ON api_usage_events(user_id,created_at);
CREATE INDEX IF NOT EXISTS idx_usage_type ON api_usage_events(event_type,created_at);
CREATE INDEX IF NOT EXISTS idx_reviews_next ON reviews(user_id,next_review_at);
CREATE TABLE IF NOT EXISTS app_settings(
    key TEXT PRIMARY KEY,
    value TEXT,
    is_secret INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
'''


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA busy_timeout=5000')
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        _migrate_v1_if_needed(db)
        _ensure_lesson_columns(db)
        _ensure_user_columns(db)
        db.executescript(SCHEMA)
        seed(db)
        db.commit()
    app.teardown_appcontext(close_db)


def _table_columns(db, table):
    try:
        return {row['name'] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}
    except sqlite3.OperationalError:
        return set()


def _migrate_v1_if_needed(db):
    cols = _table_columns(db, 'lessons')
    if not cols or 'context_key' in cols:
        return
    db.execute('PRAGMA foreign_keys=OFF')
    db.executescript('''
      ALTER TABLE lessons RENAME TO lessons_v1_backup;
      CREATE TABLE lessons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sentence_id INTEGER NOT NULL,
        context_key TEXT NOT NULL DEFAULT 'general',
        ai_model TEXT DEFAULT 'seed-v1',
        lesson_json TEXT NOT NULL,
        image_prompt TEXT,
        image_path TEXT,
        source TEXT DEFAULT 'seed',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sentence_id,context_key),
        FOREIGN KEY(sentence_id) REFERENCES sentences(id) ON DELETE CASCADE
      );
      INSERT INTO lessons(id,sentence_id,context_key,ai_model,lesson_json,image_path,source,created_at)
      SELECT id,sentence_id,
             COALESCE((SELECT context_category FROM sentences s WHERE s.id=lessons_v1_backup.sentence_id),'general'),
             ai_model,lesson_json,image_path,
             CASE WHEN ai_model LIKE 'seed%' THEN 'seed' ELSE 'legacy' END,
             created_at
      FROM lessons_v1_backup;
      DROP TABLE lessons_v1_backup;
    ''')
    db.execute('PRAGMA foreign_keys=ON')




def _ensure_user_columns(db):
    cols = _table_columns(db, 'users')
    if not cols:
        return
    if 'role' not in cols:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

def _ensure_lesson_columns(db):
    cols = _table_columns(db, 'lessons')
    if not cols:
        return
    if 'image_prompt' not in cols:
        db.execute('ALTER TABLE lessons ADD COLUMN image_prompt TEXT')
    if 'image_path' not in cols:
        db.execute('ALTER TABLE lessons ADD COLUMN image_path TEXT')
    if 'source' not in cols:
        db.execute("ALTER TABLE lessons ADD COLUMN source TEXT DEFAULT 'legacy'")


def _visual_spec(entities, action, environment, must_show, must_not_show, camera='medium close-up focused on the action'):
    return {
        'entities': entities, 'action': action, 'environment': environment,
        'must_show': must_show, 'must_not_show': must_not_show, 'camera': camera,
    }


def seed(db):
    lessons = [
      {
        'sentence': "Let's figure out what caused the collision.", 'context': 'manufacturing',
        'visual': 'Two fixture parts are touching at the wrong point while an engineer inspects the contact area.',
        'visual_spec': _visual_spec(
            ['industrial test fixture', 'moving fixture part', 'fixed fixture part', 'engineer'],
            'the two fixture parts have collided at one clearly visible unintended contact point while the engineer investigates the cause',
            'electronics manufacturing test station',
            ['one unmistakable collision/contact point', 'two distinct fixture parts', 'engineer inspecting the collision area'],
            ['cars or road traffic', 'explosion', 'broken cable as the main event', 'text labels', 'multiple unrelated accidents']
        ),
        'image_prompt': 'Clean realistic educational illustration of an electronics manufacturing test fixture with two fixture parts colliding at one unintended contact point while an engineer inspects it; factory test station; no text or labels.',
        'pronunciation': "let's FIG-yer out what kawzd the kuh-LI-zhun",
        'highlights': ['figure out', 'caused the collision'],
        'patterns': [
            {'pattern':'figure out + something','examples':['figure out the problem','figure out the root cause','figure out what happened']},
            {'pattern':'cause + problem/event','examples':['cause a collision','cause a failure','cause a delay']}
        ],
        'uses':['We need to figure out the root cause.','Can you figure out what happened?','This interference may cause a collision.'],
        'quiz':['figure out the problem','figure the problem'],'answer':0,
        'turn_prompt':'The tester suddenly stopped. Complete: We need to figure out _____.','turn_answer':'why the tester stopped'
      },
      {
        'sentence':'Can you double-check the test result before release?','context':'manufacturing',
        'visual':'An engineer compares a test result twice at a workstation before a product release approval.',
        'visual_spec': _visual_spec(
            ['engineer', 'test workstation', 'test result screen', 'product awaiting release'],
            'the engineer is carefully checking the same test result again before approving release',
            'electronics manufacturing test station',
            ['engineer actively reviewing the result', 'clear pre-release approval context', 'same result being verified again'],
            ['shipping truck', 'customer presentation', 'visible written sentence', 'random repair action']
        ),
        'image_prompt':'Clean educational illustration of an engineer carefully re-checking a test result at a manufacturing test station before product release approval; product waits beside the station; no readable text, labels or logos.',
        'pronunciation':'can you DUH-bul-check the test result before release','highlights':['double-check','before release'],
        'patterns':[{'pattern':'double-check + something','examples':['double-check the result','double-check the fixture','double-check the report']},{'pattern':'before + event','examples':['before release','before shipment','before the meeting']}],
        'uses':['Please double-check the result.','Can you double-check this fixture?','Let’s review it before release.'],
        'quiz':['double-check the result','double check again the result twice'],'answer':0,
        'turn_prompt':'A report will be sent to the customer. Complete: Please double-check _____.','turn_answer':'the report before sending it'
      },
      {
        'sentence':"I'll get back to you once I confirm with the team.",'context':'office',
        'visual':'A worker asks teammates for confirmation, then prepares to reply to a waiting message.',
        'visual_spec': _visual_spec(
            ['office worker', 'two teammates', 'laptop or phone with waiting message'],
            'the worker is confirming information with teammates before replying to the waiting person',
            'modern workplace collaboration area',
            ['worker consulting teammates first', 'waiting communication device visible', 'sequence clearly implies reply happens after confirmation'],
            ['worker already sending the final reply before confirmation', 'customer angry scene', 'visible readable chat text', 'phone call as the only action']
        ),
        'image_prompt':'Clean educational workplace illustration: one office worker briefly confirms information with two teammates while a laptop/phone nearby shows an unreadable waiting message, clearly implying they will reply afterward; no readable text or labels.',
        'pronunciation':"I'll get BACK to you once I confirm with the team",'highlights':['get back to you','confirm with the team'],
        'patterns':[{'pattern':'get back to + someone','examples':['get back to you','get back to the customer','get back to my manager']},{'pattern':'confirm with + someone','examples':['confirm with the team','confirm with engineering','confirm with the supplier']}],
        'uses':["I'll get back to you this afternoon.","Let me confirm with the team first.","I'll update you once I know more."],
        'quiz':["I'll get back to you.","I'll return back to you later."],'answer':0,
        'turn_prompt':'You need more information before answering. Write a natural reply.','turn_answer':"I'll get back to you once I confirm with the team."
      }
    ]
    for item in lessons:
        norm = ' '.join(item['sentence'].lower().split())
        db.execute('INSERT OR IGNORE INTO sentences(original_text,normalized_text,context_category) VALUES(?,?,?)', (item['sentence'], norm, item['context']))
        sid = db.execute('SELECT id FROM sentences WHERE normalized_text=?', (norm,)).fetchone()['id']
        db.execute(
            '''INSERT OR IGNORE INTO lessons(sentence_id,context_key,ai_model,lesson_json,image_prompt,source)
               VALUES(?,?,?,?,?,?)''',
            (sid, item['context'], 'seed-v1.2', json.dumps(item, ensure_ascii=False), item['image_prompt'], 'seed')
        )
        for p in item['patterns']:
            db.execute(
                '''INSERT INTO patterns(pattern,example_json,frequency) VALUES(?,?,1)
                   ON CONFLICT(pattern) DO UPDATE SET frequency=patterns.frequency+1''',
                (p['pattern'], json.dumps(p['examples'], ensure_ascii=False))
            )
            pid = db.execute('SELECT id FROM patterns WHERE pattern=?', (p['pattern'],)).fetchone()['id']
            db.execute('INSERT OR IGNORE INTO sentence_patterns(sentence_id,pattern_id) VALUES(?,?)', (sid, pid))
