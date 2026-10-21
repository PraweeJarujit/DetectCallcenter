"""
Benchmark: รัน query จริงของ API บน 2 database (มี index / ไม่มี index) แล้วเทียบเวลา

    pip install psycopg2-binary
    python scripts/benchmark.py                       # ใช้ค่า default ของ docker-compose ใน db-indexing/
    python scripts/benchmark.py --with "postgresql://student:student@localhost:5442/appdb" \
                                --without "postgresql://student:student@localhost:5443/appdb" \
                                --runs 7 --out results/benchmark.md

วิธีวัด: EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) -> ใช้ "Execution Time" ฝั่ง server
(ไม่รวม network) วอร์มอัป 1 รอบ แล้วเอา median ของ N รอบ
query ที่แก้ข้อมูล (DELETE) รันใน transaction แล้ว ROLLBACK ทุกครั้ง ข้อมูลไม่หายจริง
"""
import argparse
import json
import statistics
import sys
from datetime import datetime

import psycopg2

TODAY = "2026-10-02 00:00+07"          # "วันนี้" ของ lab (ตรงกับ seed)
WEEK_START = "2026-09-26 00:00+07"     # 7 วันล่าสุด (รวมวันนี้)

# (รหัส, endpoint, คำอธิบาย, SQL, index ที่ควรถูกใช้)
QUERIES = [
    ("Q1", "POST /detect/number", "ค้นเบอร์ตรงตัว",
     "SELECT * FROM blacklist_numbers WHERE phone_number = %(phone)s", "IDX-1 (มีทั้ง 2 DB)"),
    ("Q2", "GET /blacklist?q=", "ค้นเบอร์ขึ้นต้นด้วย (prefix)",
     "SELECT * FROM blacklist_numbers WHERE phone_number LIKE %(prefix)s "
     "ORDER BY risk_score DESC, id LIMIT 20", "IDX-1 (มีทั้ง 2 DB)"),
    ("Q3", "GET /blacklist?status=high_risk", "กรองสถานะ + เรียงตาม risk หน้าแรก",
     "SELECT * FROM blacklist_numbers WHERE status = 'high_risk' "
     "ORDER BY risk_score DESC, id LIMIT 20", "IDX-2"),
    ("Q4", "GET /blacklist", "ทั้งหมด เรียงตาม risk หน้าแรก",
     "SELECT * FROM blacklist_numbers ORDER BY risk_score DESC, id LIMIT 20", "IDX-3"),
    ("Q5", "GET /blacklist/{phone}", "report ล่าสุดของเบอร์",
     "SELECT * FROM reports WHERE blacklist_number_id = %(bl_id)s ORDER BY created_at DESC LIMIT 50", "IDX-4"),
    ("Q6", "GET /reports/me", "report ของฉัน หน้าแรก",
     "SELECT * FROM reports WHERE reported_by = %(user_id)s ORDER BY created_at DESC LIMIT 20", "IDX-5"),
    ("Q7", "GET /reports/me", "นับ report ของฉัน (total)",
     "SELECT count(*) FROM reports WHERE reported_by = %(user_id)s", "IDX-5"),
    ("Q8", "GET /calls/stats", "จำนวนสายวันนี้",
     f"SELECT count(*) FROM call_logs WHERE created_at >= '{TODAY}'", "IDX-6"),
    ("Q9", "GET /calls/stats", "สายเสี่ยงสูงวันนี้",
     f"SELECT count(*) FROM call_logs WHERE created_at >= '{TODAY}' AND risk_score >= 80", "IDX-7 partial"),
    ("Q10", "GET /calls/trend", "สายเสี่ยงสูงรายวัน 7 วัน",
     "SELECT date(timezone('Asia/Bangkok', created_at)) d, count(*) FROM call_logs "
     f"WHERE created_at >= '{WEEK_START}' AND risk_score >= 80 GROUP BY 1", "IDX-7 partial"),
    ("Q11", "GET /calls/logs", "Call Logs ล่าสุด 20 แถว",
     "SELECT * FROM call_logs ORDER BY created_at DESC, id DESC LIMIT 21", "IDX-6"),
    ("Q12", "GET /calls/logs?before_id=", "หน้าถัดไปแบบ keyset (ลึก ~1 แสนแถว)",
     "SELECT * FROM call_logs WHERE (created_at, id) < (%(cursor_at)s, %(cursor_id)s) "
     "ORDER BY created_at DESC, id DESC LIMIT 21", "IDX-6"),
    ("Q13", "GET /calls/logs?mine=true", "ประวัติการตรวจของฉัน",
     "SELECT * FROM call_logs WHERE user_id = %(user_id)s ORDER BY created_at DESC, id DESC LIMIT 21", "IDX-8 partial"),
    ("Q14", "GET /contacts", "ผู้ติดต่อฉุกเฉินของฉัน",
     "SELECT * FROM emergency_contacts WHERE user_id = %(user_id)s ORDER BY created_at", "IDX-9"),
    ("Q15", "(สถิติ)", "จำนวน report ตามหมวด (M-N ค้นกลับ)",
     "SELECT count(*) FROM report_categories WHERE category_id = 7", "ix_report_categories_category"),
    ("Q16", "DELETE /blacklist/{phone}", "ลบเบอร์ -> CASCADE ลบ reports",
     "DELETE FROM blacklist_numbers WHERE id = %(bl_id)s", "IDX-4 (FK)"),
    ("Q17", "DELETE /users/{id}", "ลบ user -> SET NULL ใน reports/call_logs + CASCADE contacts",
     "DELETE FROM users WHERE id = %(user_id)s", "IDX-5, IDX-8, IDX-9 (FK)"),
]


def collect_nodes(plan, out):
    label = plan["Node Type"]
    if plan.get("Index Name"):
        label += f" ({plan['Index Name']})"
    out.append(label)
    for child in plan.get("Plans", []):
        collect_nodes(child, out)
    return out


def summarize(plan_json):
    root = plan_json[0]
    nodes = collect_nodes(root["Plan"], [])
    interesting = [n for n in nodes if any(k in n for k in ("Scan", "Sort"))]
    trig = sum(t.get("Time", 0) for t in root.get("Triggers", []))
    return " → ".join(dict.fromkeys(interesting)) or nodes[0], root["Execution Time"], trig


def params_for(conn):
    with conn.cursor() as cur:
        # เบอร์ที่ถูกแจ้งมากที่สุด (เลือกด้วยเบอร์ ไม่ใช่ uuid -> 2 DB ได้เบอร์เดียวกัน)
        cur.execute("SELECT id, phone_number FROM blacklist_numbers ORDER BY report_count DESC, phone_number LIMIT 1")
        bl_id, phone = cur.fetchone()
        cur.execute("SELECT id FROM users WHERE username = 'user7'")
        (user_id,) = cur.fetchone()
        cur.execute("SELECT created_at, id FROM call_logs ORDER BY created_at DESC, id DESC OFFSET 100000 LIMIT 1")
        cursor_at, cursor_id = cur.fetchone()
    return {"bl_id": bl_id, "phone": phone, "prefix": phone[:5] + "%", "user_id": user_id,
            "cursor_at": cursor_at, "cursor_id": cursor_id}


def run_one(conn, sql, params, runs):
    is_write = sql.lstrip().upper().startswith("DELETE")
    times, trig_times, summary = [], [], ""
    with conn.cursor() as cur:
        for i in range(runs + 1):  # รอบแรก = warm-up
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
            plan = cur.fetchone()[0]
            if isinstance(plan, str):
                plan = json.loads(plan)
            if is_write:
                conn.rollback()
            summary, exec_ms, trig_ms = summarize(plan)
            if i > 0:
                times.append(exec_ms)
                trig_times.append(trig_ms)
    if not is_write:
        conn.rollback()
    return statistics.median(times), summary


def fmt_ms(ms):
    return f"{ms:,.2f}" if ms < 100 else f"{ms:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with", dest="with_url", default="postgresql://student:student@localhost:5442/appdb")
    ap.add_argument("--without", dest="without_url", default="postgresql://student:student@localhost:5443/appdb")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default="results/benchmark.md")
    args = ap.parse_args()

    conns = {"with": psycopg2.connect(args.with_url), "without": psycopg2.connect(args.without_url)}
    params = {k: params_for(c) for k, c in conns.items()}
    with conns["with"].cursor() as cur:
        cur.execute("SELECT version()")
        version = cur.fetchone()[0].split(" on ")[0]

    rows = []
    for code, endpoint, desc, sql, idx in QUERIES:
        res = {k: run_one(c, sql, params[k], args.runs) for k, c in conns.items()}
        (t_no, plan_no), (t_with, plan_with) = res["without"], res["with"]
        speedup = t_no / t_with if t_with > 0 else float("inf")
        rows.append((code, endpoint, desc, idx, t_no, t_with, speedup, plan_no, plan_with))
        print(f"{code:4} {desc:45} no-index {fmt_ms(t_no):>9} ms | with-index {fmt_ms(t_with):>8} ms | x{speedup:,.0f}",
              file=sys.stderr)

    lines = [
        "# ผล Benchmark: query จริงของ AwayCall API — มี index vs ไม่มี index",
        "",
        f"- วันที่วัด: {datetime.now():%Y-%m-%d %H:%M}  |  {version}",
        "- ข้อมูล: call_logs 2,000,000 · reports 600,000 · report_categories ~860,000 · "
        "blacklist_numbers 200,000 · users 1,000",
        f"- เวลา = median ของ {args.runs} รอบ (Execution Time จาก EXPLAIN ANALYZE, หน่วย ms) หลังวอร์มอัป 1 รอบ",
        "- ตัวเลขขึ้นกับเครื่อง ให้ดู \"อัตราส่วน\" และ \"plan\" เป็นหลัก",
        "",
        "| # | Endpoint | Query | Index ที่ออกแบบไว้ | ไม่มี index (ms) | มี index (ms) | เร็วขึ้น |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for code, endpoint, desc, idx, t_no, t_with, sp, _, _ in rows:
        sp_txt = f"**{sp:,.0f}×**" if sp >= 2 else f"{sp:,.1f}×"
        lines.append(f"| {code} | `{endpoint}` | {desc} | {idx} | {fmt_ms(t_no)} | {fmt_ms(t_with)} | {sp_txt} |")
    lines += ["", "## Plan ที่ได้ (node ที่อ่านข้อมูล/เรียงข้อมูล)", "",
              "| # | ไม่มี index | มี index |", "|---|---|---|"]
    for code, _, _, _, _, _, _, p_no, p_with in rows:
        lines.append(f"| {code} | {p_no} | {p_with} |")
    lines.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
