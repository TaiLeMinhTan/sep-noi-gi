import Database from "better-sqlite3";
import bcrypt from "bcryptjs";

const db = new Database("workplace-v2.db");
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT '',
  age_group TEXT NOT NULL DEFAULT '',
  industry TEXT NOT NULL DEFAULT '',
  job_role TEXT NOT NULL DEFAULT '',
  learning_goal TEXT NOT NULL DEFAULT '',
  native_language TEXT NOT NULL DEFAULT 'vi',
  learning_languages_json TEXT NOT NULL DEFAULT '[]',
  onboarding_completed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sentences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  original_text TEXT NOT NULL,
  source_language TEXT NOT NULL DEFAULT 'auto',
  target_language TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Workplace',
  analysis_json TEXT NOT NULL DEFAULT '{}',
  notes TEXT NOT NULL DEFAULT '',
  favorite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS study_progress (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  sentence_id INTEGER NOT NULL,
  level INTEGER NOT NULL DEFAULT 0,
  review_count INTEGER NOT NULL DEFAULT 0,
  last_reviewed_at TEXT,
  UNIQUE(user_id, sentence_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(sentence_id) REFERENCES sentences(id) ON DELETE CASCADE
);
`);

export function seedDemoData() {
  const email = "demo@sepnoigi.local";
  let user = db.prepare("SELECT * FROM users WHERE email = ?").get(email);
  if (!user) {
    const result = db.prepare(`
      INSERT INTO users
      (name,email,password_hash,country,age_group,industry,job_role,learning_goal,native_language,learning_languages_json,onboarding_completed)
      VALUES (?,?,?,?,?,?,?,?,?,?,1)
    `).run(
      "Min Demo",
      email,
      bcrypt.hashSync("demo1234", 10),
      "Vietnam",
      "25-34",
      "Manufacturing / Electronics",
      "Test Engineer",
      "Improve workplace English for meetings, reports and career growth",
      "vi",
      JSON.stringify([
        { code: "en", level: "intermediate" },
        { code: "zh", level: "intermediate" }
      ])
    );
    user = db.prepare("SELECT * FROM users WHERE id = ?").get(result.lastInsertRowid);
  }

  const count = db.prepare("SELECT COUNT(*) AS n FROM sentences WHERE user_id = ?").get(user.id).n;
  if (count) return;

  const insert = db.prepare(`
    INSERT INTO sentences
    (user_id,original_text,source_language,target_language,category,analysis_json,notes,favorite)
    VALUES (?,?,?,?,?,?,?,?)
  `);

  const samples = [
    {
      text: "Let's align on the next steps and set a clear timeline.", target: "en", category: "Meeting", favorite: 1,
      analysis: {
        chunk: "Let's align on this.", pronunciation: "/lets əˈlaɪn ɒn ðɪs/",
        plain_description: "Use this when you want everyone to share the same understanding before moving forward.",
        usage: "Common in meetings, project discussions and cross-team work.", image_key: "meeting",
        related_chunks: ["be on the same page","get aligned","clarify","confirm","move forward"],
        examples: [
          {text:"Let's align on the test plan and timeline.",situation:"Manufacturing",image_key:"factory"},
          {text:"Let's align on the next steps and assign owners.",situation:"Team meeting",image_key:"meeting"}
        ],
        vocabulary: [{word:"align",definition:"to bring people, goals or plans into agreement",image_key:"meeting"}],
        suggested_replies:["Absolutely. Let's confirm the goal and next steps."]
      }
    },
    {
      text: "Please double-check this issue before releasing it to production.", target: "en", category: "Manufacturing", favorite: 1,
      analysis: {
        chunk:"double-check this", pronunciation:"/ˌdʌbəl ˈtʃek ðɪs/",
        plain_description:"Use this when one more careful verification is needed before an important action.",
        usage:"Common in testing, quality control and release decisions.", image_key:"factory",
        related_chunks:["verify it again","make sure","confirm the result","check one more time"],
        examples:[{text:"Please double-check this result before release.",situation:"Testing",image_key:"factory"}],
        vocabulary:[{word:"verify",definition:"to check that something is true, accurate or acceptable",image_key:"factory"}],
        suggested_replies:["Sure. I'll verify it again before release."]
      }
    }
  ];

  for (const item of samples) {
    insert.run(
      user.id,
      item.text,
      "auto",
      item.target,
      item.category,
      JSON.stringify(item.analysis),
      "",
      item.favorite
    );
  }
}

export default db;
