import "dotenv/config";
import express from "express";
import session from "express-session";
import bcrypt from "bcryptjs";
import path from "path";
import { fileURLToPath } from "url";
import db, { seedDemoData } from "./db.js";
import { analyzeSentence, supportedLanguages, aiCapabilities } from "./ai.js";

seedDemoData();

const app = express();
const PORT = Number(process.env.PORT || 3000);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

app.use(express.json({ limit: "300kb" }));
app.use(session({
  secret: process.env.SESSION_SECRET || "dev-change-me-v2-1",
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    maxAge: 7 * 24 * 60 * 60 * 1000
  }
}));
app.use(express.static(path.join(__dirname, "public")));

const clean = (value, max = 3000) => String(value ?? "").trim().slice(0, max);
const parseJson = (text, fallback) => {
  try { return JSON.parse(text); } catch { return fallback; }
};
const requireAuth = (req, res, next) => {
  if (!req.session.userId) return res.status(401).json({ error: "Please log in first." });
  next();
};

function userView(row) {
  if (!row) return null;
  return {
    id: row.id,
    name: row.name,
    email: row.email,
    country: row.country,
    age_group: row.age_group,
    industry: row.industry,
    job_role: row.job_role,
    learning_goal: row.learning_goal,
    native_language: row.native_language,
    learning_languages: parseJson(row.learning_languages_json, []),
    onboarding_completed: Boolean(row.onboarding_completed),
    created_at: row.created_at
  };
}

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, version: "2.2.0", ai_provider: process.env.AI_PROVIDER || "demo" });
});

app.get("/api/languages", (_req, res) => res.json(supportedLanguages()));
app.get("/api/ai/capabilities", (_req, res) => res.json(aiCapabilities()));

app.post("/api/auth/register", (req, res) => {
  const name = clean(req.body.name, 80);
  const email = clean(req.body.email, 160).toLowerCase();
  const password = clean(req.body.password, 200);

  if (name.length < 2 || !email.includes("@") || password.length < 8) {
    return res.status(400).json({ error: "Please enter a valid name, email and password (8+ characters)." });
  }
  if (db.prepare("SELECT id FROM users WHERE email = ?").get(email)) {
    return res.status(409).json({ error: "Email already registered." });
  }

  const result = db.prepare("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)")
    .run(name, email, bcrypt.hashSync(password, 10));
  req.session.userId = Number(result.lastInsertRowid);
  res.status(201).json({ user: userView(db.prepare("SELECT * FROM users WHERE id=?").get(result.lastInsertRowid)) });
});

app.post("/api/auth/login", (req, res) => {
  const email = clean(req.body.email, 160).toLowerCase();
  const user = db.prepare("SELECT * FROM users WHERE email = ?").get(email);
  if (!user || !bcrypt.compareSync(clean(req.body.password, 200), user.password_hash)) {
    return res.status(401).json({ error: "Incorrect email or password." });
  }
  req.session.userId = user.id;
  res.json({ user: userView(user) });
});

app.post("/api/auth/logout", (req, res) => req.session.destroy(() => res.json({ ok: true })));
app.get("/api/auth/me", (req, res) => {
  const row = req.session.userId ? db.prepare("SELECT * FROM users WHERE id=?").get(req.session.userId) : null;
  res.json({ user: userView(row) });
});

app.put("/api/profile", requireAuth, (req, res) => {
  const languages = Array.isArray(req.body.learning_languages)
    ? req.body.learning_languages
        .filter((item) => item && item.code)
        .slice(0, 12)
        .map((item) => ({ code: clean(item.code, 12), level: clean(item.level, 30) || "beginner" }))
    : [];

  db.prepare(`
    UPDATE users SET
      name=?, country=?, age_group=?, industry=?, job_role=?, learning_goal=?,
      native_language=?, learning_languages_json=?, onboarding_completed=1
    WHERE id=?
  `).run(
    clean(req.body.name, 80) || db.prepare("SELECT name FROM users WHERE id=?").get(req.session.userId).name,
    clean(req.body.country, 80),
    clean(req.body.age_group, 30),
    clean(req.body.industry, 120),
    clean(req.body.job_role, 120),
    clean(req.body.learning_goal, 250),
    clean(req.body.native_language, 12) || "vi",
    JSON.stringify(languages),
    req.session.userId
  );

  res.json({ user: userView(db.prepare("SELECT * FROM users WHERE id=?").get(req.session.userId)) });
});

app.get("/api/dashboard", requireAuth, (req, res) => {
  const uid = req.session.userId;
  const user = userView(db.prepare("SELECT * FROM users WHERE id=?").get(uid));
  const total = db.prepare("SELECT COUNT(*) AS n FROM sentences WHERE user_id=?").get(uid).n;
  const favorites = db.prepare("SELECT COUNT(*) AS n FROM sentences WHERE user_id=? AND favorite=1").get(uid).n;
  const reviewed = db.prepare("SELECT COALESCE(SUM(review_count),0) AS n FROM study_progress WHERE user_id=?").get(uid).n;
  const learned = db.prepare("SELECT COUNT(*) AS n FROM study_progress WHERE user_id=? AND level>=3").get(uid).n;
  const categories = db.prepare("SELECT category,COUNT(*) AS count FROM sentences WHERE user_id=? GROUP BY category ORDER BY count DESC").all(uid);

  res.json({
    user,
    stats: {
      total,
      favorites,
      reviewed,
      learned,
      streak: total ? Math.min(12, total + 2) : 0,
      minutes: total ? Math.max(18, total * 8) : 0
    },
    categories
  });
});

app.get("/api/sentences", requireAuth, (req, res) => {
  const query = clean(req.query.search, 120);
  const target = clean(req.query.target, 12);
  const like = `%${query}%`;
  const rows = db.prepare(`
    SELECT s.*, COALESCE(p.level,0) AS study_level, COALESCE(p.review_count,0) AS review_count
    FROM sentences s
    LEFT JOIN study_progress p ON p.user_id=s.user_id AND p.sentence_id=s.id
    WHERE s.user_id=?
      AND (?='' OR s.original_text LIKE ? OR s.analysis_json LIKE ? OR s.category LIKE ?)
      AND (?='' OR s.target_language=?)
    ORDER BY s.id DESC
  `).all(req.session.userId, query, like, like, like, target, target);

  res.json(rows.map((row) => ({ ...row, analysis: parseJson(row.analysis_json, {}) })));
});

app.post("/api/ai/analyze", requireAuth, async (req, res) => {
  const text = clean(req.body.text);
  const targetLanguage = clean(req.body.target_language, 12) || "en";
  if (!text) return res.status(400).json({ error: "Enter a sentence first." });
  const user = userView(db.prepare("SELECT * FROM users WHERE id=?").get(req.session.userId));
  res.json(await analyzeSentence({ text, targetLanguage, user }));
});

app.post("/api/sentences", requireAuth, (req, res) => {
  const text = clean(req.body.original_text);
  if (!text) return res.status(400).json({ error: "Sentence is required." });
  const analysis = req.body.analysis && typeof req.body.analysis === "object" ? req.body.analysis : {};
  const result = db.prepare(`
    INSERT INTO sentences(user_id,original_text,source_language,target_language,category,analysis_json,notes)
    VALUES(?,?,?,?,?,?,?)
  `).run(
    req.session.userId,
    text,
    clean(req.body.source_language, 12) || "auto",
    clean(req.body.target_language, 12) || "en",
    clean(req.body.category, 80) || analysis.category || "Workplace",
    JSON.stringify(analysis),
    clean(req.body.notes, 3000)
  );
  res.status(201).json({ id: Number(result.lastInsertRowid) });
});

app.put("/api/sentences/:id", requireAuth, (req, res) => {
  const id = Number(req.params.id);
  const row = db.prepare("SELECT * FROM sentences WHERE id=? AND user_id=?").get(id, req.session.userId);
  if (!row) return res.status(404).json({ error: "Not found." });

  const analysis = req.body.analysis && typeof req.body.analysis === "object"
    ? req.body.analysis
    : parseJson(row.analysis_json, {});

  db.prepare(`
    UPDATE sentences SET original_text=?, target_language=?, category=?, analysis_json=?, notes=?
    WHERE id=? AND user_id=?
  `).run(
    clean(req.body.original_text, 3000) || row.original_text,
    clean(req.body.target_language, 12) || row.target_language,
    clean(req.body.category, 80) || row.category,
    JSON.stringify(analysis),
    clean(req.body.notes, 3000),
    id,
    req.session.userId
  );
  res.json({ ok: true });
});

app.put("/api/sentences/:id/favorite", requireAuth, (req, res) => {
  const id = Number(req.params.id);
  const row = db.prepare("SELECT favorite FROM sentences WHERE id=? AND user_id=?").get(id, req.session.userId);
  if (!row) return res.status(404).json({ error: "Not found." });
  const favorite = row.favorite ? 0 : 1;
  db.prepare("UPDATE sentences SET favorite=? WHERE id=? AND user_id=?").run(favorite, id, req.session.userId);
  res.json({ favorite });
});

app.delete("/api/sentences/:id", requireAuth, (req, res) => {
  db.prepare("DELETE FROM sentences WHERE id=? AND user_id=?").run(Number(req.params.id), req.session.userId);
  res.json({ ok: true });
});

app.get("/api/flashcards", requireAuth, (req, res) => {
  const rows = db.prepare(`
    SELECT s.*, COALESCE(p.level,0) AS study_level
    FROM sentences s
    LEFT JOIN study_progress p ON p.user_id=s.user_id AND p.sentence_id=s.id
    WHERE s.user_id=?
    ORDER BY COALESCE(p.level,0), RANDOM()
    LIMIT 50
  `).all(req.session.userId);
  res.json(rows.map((row) => ({ ...row, analysis: parseJson(row.analysis_json, {}) })));
});

app.post("/api/flashcards/:id/review", requireAuth, (req, res) => {
  const id = Number(req.params.id);
  const sentence = db.prepare("SELECT id FROM sentences WHERE id=? AND user_id=?").get(id, req.session.userId);
  if (!sentence) return res.status(404).json({ error: "Not found." });

  const rating = ["again", "hard", "good", "easy"].includes(req.body.rating) ? req.body.rating : "good";
  const current = db.prepare("SELECT * FROM study_progress WHERE user_id=? AND sentence_id=?").get(req.session.userId, id);
  let level = current?.level || 0;
  if (rating === "again") level = Math.max(0, level - 1);
  if (rating === "hard") level = Math.max(1, level);
  if (rating === "good") level = Math.min(5, level + 1);
  if (rating === "easy") level = Math.min(5, level + 2);

  db.prepare(`
    INSERT INTO study_progress(user_id,sentence_id,level,review_count,last_reviewed_at)
    VALUES(?,?,?,1,CURRENT_TIMESTAMP)
    ON CONFLICT(user_id,sentence_id) DO UPDATE SET
      level=excluded.level,
      review_count=study_progress.review_count+1,
      last_reviewed_at=CURRENT_TIMESTAMP
  `).run(req.session.userId, id, level);
  res.json({ level });
});

// Express 5 compatible SPA fallback.
app.get("/{*splat}", (_req, res) => res.sendFile(path.join(__dirname, "public", "index.html")));

app.listen(PORT, () => {
  console.log(`\nSếp Nói Gì? v2.2 running at http://localhost:${PORT}`);
  console.log("Demo account: demo@sepnoigi.local / demo1234\n");
});
