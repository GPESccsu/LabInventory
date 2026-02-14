import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "smoke_ledger.db"
INV = ["python", "inv.py", "--db", str(DB)]


def run(args):
    cmd = INV + args
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout.strip()


if DB.exists():
    DB.unlink()
sqlite3.connect(DB).close()

run(["init-locations", "--room", "C409", "--g01-shelves", "1", "--g02-shelves", "0", "--positions", "2"])

conn = sqlite3.connect(DB)
conn.execute("INSERT INTO parts (mpn,name,category,unit) VALUES (?,?,?,?)", ("SMOKE-LEDGER-001", "Smoke Part", "Test", "pcs"))
conn.commit()
conn.close()

run(["proj-new", "--code", "PJ-SMOKE", "--name", "Smoke Project"])
run(["stock-in", "--mpn", "SMOKE-LEDGER-001", "--loc", "C409-G01-S01-P01", "--qty", "100", "--note", "smoke in"])
run(["stock-out", "--mpn", "SMOKE-LEDGER-001", "--loc", "C409-G01-S01-P01", "--qty", "30", "--proj", "PJ-SMOKE", "--note", "smoke out"])
run(["stock-move", "--mpn", "SMOKE-LEDGER-001", "--from", "C409-G01-S01-P01", "--to", "C409-G01-S01-P02", "--qty", "20", "--note", "smoke move"])
run(["stock-adjust", "--mpn", "SMOKE-LEDGER-001", "--loc", "C409-G01-S01-P02", "--sub", "10", "--note", "smoke adjust"])
reserve_out = run(["reserve", "--proj", "PJ-SMOKE", "--mpn", "SMOKE-LEDGER-001", "--loc", "C409-G01-S01-P02", "--qty", "10", "--note", "smoke reserve"])
alloc_id = int(reserve_out.split("alloc_id=")[1].split()[0])
run(["consume", "--id", str(alloc_id), "--note", "smoke consume"])

conn = sqlite3.connect(DB)
part_id = conn.execute("SELECT id FROM parts WHERE mpn='SMOKE-LEDGER-001'").fetchone()[0]
q1 = conn.execute("SELECT qty FROM stock WHERE part_id=? AND location='C409-G01-S01-P01'", (part_id,)).fetchone()[0]
q2 = conn.execute("SELECT qty FROM stock WHERE part_id=? AND location='C409-G01-S01-P02'", (part_id,)).fetchone()[0]
count_doc = conn.execute("SELECT COUNT(*) FROM inv_doc").fetchone()[0]
conn.close()

assert q1 == 50, q1
assert q2 == 0, q2
assert count_doc == 6, count_doc
print("smoke_test_ledger: PASS")
