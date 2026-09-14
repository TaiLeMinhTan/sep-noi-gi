import json
import os
from datetime import datetime, timedelta
from database import get_db

# Defaults are snapshots of OpenAI API pricing verified 2026-09-06.
# Override any rate in .env without code changes.
DEFAULT_RATES = {
    'gpt-5.6-luna': {'text_input_per_m': 0.20, 'text_cached_input_per_m': 0.02, 'text_output_per_m': 1.20},
    'gpt-5.6-terra': {'text_input_per_m': 2.00, 'text_cached_input_per_m': 0.20, 'text_output_per_m': 12.00},
    'gpt-5.6-sol': {'text_input_per_m': 4.00, 'text_cached_input_per_m': 0.40, 'text_output_per_m': 20.00},
    # GPT-Image-2: text input $5/M, cached $1.25/M; image input $8/M, cached $2/M; image output $30/M.
    'gpt-image-2': {'text_input_per_m': 5.00, 'text_cached_input_per_m': 1.25, 'text_output_per_m': 10.00,
                    'image_input_per_m': 8.00, 'image_cached_input_per_m': 2.00, 'image_output_per_m': 30.00},
}


def _env_rate(model, key, fallback):
    env_key = 'PRICE_' + model.upper().replace('-', '_').replace('.', '_') + '_' + key.upper()
    try:
        return float(os.getenv(env_key, fallback))
    except (TypeError, ValueError):
        return float(fallback)


def rates_for(model):
    base = DEFAULT_RATES.get(model, DEFAULT_RATES['gpt-5.6-luna']).copy()
    return {k: _env_rate(model, k, v) for k, v in base.items()}


def calculate_cost(model, *, input_tokens=0, cached_input_tokens=0, output_tokens=0,
                   image_input_tokens=0, image_output_tokens=0):
    r = rates_for(model)
    cost = (
        int(input_tokens or 0) * r.get('text_input_per_m', 0)
        + int(cached_input_tokens or 0) * r.get('text_cached_input_per_m', 0)
        + int(output_tokens or 0) * r.get('text_output_per_m', 0)
        + int(image_input_tokens or 0) * r.get('image_input_per_m', 0)
        + int(image_output_tokens or 0) * r.get('image_output_per_m', 0)
    ) / 1_000_000
    return cost, r


def record_usage(*, user_id, event_type, model, lesson_id=None, visual_asset_id=None,
                 request_id=None, input_tokens=0, cached_input_tokens=0, output_tokens=0,
                 image_input_tokens=0, image_output_tokens=0, metadata=None):
    cost, rates = calculate_cost(
        model, input_tokens=input_tokens, cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens, image_input_tokens=image_input_tokens,
        image_output_tokens=image_output_tokens,
    )
    db = get_db()
    db.execute('''INSERT INTO api_usage_events(
        user_id,event_type,model,lesson_id,visual_asset_id,request_id,
        input_tokens,cached_input_tokens,output_tokens,image_input_tokens,image_output_tokens,
        cost_usd,pricing_snapshot_json,metadata_json
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        user_id,event_type,model,lesson_id,visual_asset_id,request_id,
        int(input_tokens or 0),int(cached_input_tokens or 0),int(output_tokens or 0),
        int(image_input_tokens or 0),int(image_output_tokens or 0),cost,
        json.dumps(rates),json.dumps(metadata or {}, ensure_ascii=False)
    ))
    db.commit()
    return cost


def dashboard_payload(days=30):
    db = get_db()
    days = max(1, min(3650, int(days)))
    since = (datetime.now() - timedelta(days=days-1)).strftime('%Y-%m-%d 00:00:00')
    summary = db.execute('''SELECT COUNT(*) calls, COALESCE(SUM(cost_usd),0) cost,
        COALESCE(SUM(input_tokens),0) input_tokens, COALESCE(SUM(output_tokens),0) output_tokens,
        COALESCE(SUM(image_output_tokens),0) image_output_tokens
        FROM api_usage_events WHERE created_at>=?''',(since,)).fetchone()
    by_type = db.execute('''SELECT event_type,COUNT(*) calls,COALESCE(SUM(cost_usd),0) cost
        FROM api_usage_events WHERE created_at>=? GROUP BY event_type ORDER BY cost DESC''',(since,)).fetchall()
    by_model = db.execute('''SELECT model,COUNT(*) calls,COALESCE(SUM(cost_usd),0) cost
        FROM api_usage_events WHERE created_at>=? GROUP BY model ORDER BY cost DESC''',(since,)).fetchall()
    daily = db.execute('''SELECT date(created_at) day,COUNT(*) calls,COALESCE(SUM(cost_usd),0) cost
        FROM api_usage_events WHERE created_at>=? GROUP BY date(created_at) ORDER BY day''',(since,)).fetchall()
    by_user = db.execute('''SELECT COALESCE(u.email,'deleted') user,COUNT(e.id) calls,COALESCE(SUM(e.cost_usd),0) cost
        FROM api_usage_events e LEFT JOIN users u ON u.id=e.user_id
        WHERE e.created_at>=? GROUP BY e.user_id ORDER BY cost DESC LIMIT 20''',(since,)).fetchall()
    total_users = db.execute("SELECT COUNT(*) c FROM users WHERE role='user'").fetchone()['c']
    lessons = db.execute("SELECT COUNT(*) c FROM lessons").fetchone()['c']
    visuals = db.execute("SELECT COUNT(*) c FROM visual_assets WHERE status='accepted'").fetchone()['c']
    cache = db.execute('''SELECT COUNT(*) total, COALESCE(SUM(cache_hit),0) hits FROM ai_requests WHERE created_at>=?''',(since,)).fetchone()
    cache_rate = (cache['hits']/cache['total']*100) if cache['total'] else 0
    # Estimate savings: cache hits * average paid lesson-generation cost in period.
    lesson_avg = db.execute("SELECT COALESCE(AVG(cost_usd),0) a FROM api_usage_events WHERE event_type='lesson_text' AND created_at>=?",(since,)).fetchone()['a']
    savings = cache['hits'] * lesson_avg
    month_cost = db.execute("SELECT COALESCE(SUM(cost_usd),0) c FROM api_usage_events WHERE strftime('%Y-%m',created_at)=strftime('%Y-%m','now','localtime')").fetchone()['c']
    budget = float(os.getenv('ADMIN_MONTHLY_BUDGET_USD','20'))
    return {
        'days':days,'summary':dict(summary),'by_type':[dict(x) for x in by_type],
        'by_model':[dict(x) for x in by_model],'daily':[dict(x) for x in daily],
        'by_user':[dict(x) for x in by_user],'total_users':total_users,'lessons':lessons,'visuals':visuals,
        'cache_rate':cache_rate,'cache_hits':cache['hits'],'estimated_savings':savings,
        'month_cost':month_cost,'monthly_budget':budget,'budget_pct':(month_cost/budget*100 if budget else 0)
    }
