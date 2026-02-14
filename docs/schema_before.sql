CREATE TABLE parts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  mpn           TEXT NOT NULL,
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,
  package       TEXT,
  params        TEXT,
  unit          TEXT NOT NULL DEFAULT 'pcs',
  url           TEXT,
  datasheet     TEXT,
  note          TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE UNIQUE INDEX idx_parts_mpn ON parts(mpn);
CREATE INDEX idx_parts_search ON parts(name, category);
CREATE TABLE stock (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  part_id       INTEGER NOT NULL,
  location      TEXT NOT NULL,
  qty           INTEGER NOT NULL DEFAULT 0,
  condition     TEXT NOT NULL DEFAULT 'new',
  updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  note          TEXT,
  FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);
CREATE INDEX idx_stock_part ON stock(part_id);
CREATE INDEX idx_stock_loc  ON stock(location);
CREATE TABLE locations (
  location   TEXT PRIMARY KEY,
  note       TEXT
);
CREATE TABLE projects (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  owner       TEXT,
  status      TEXT NOT NULL DEFAULT 'active',
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE project_bom (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL,
  part_id     INTEGER NOT NULL,
  req_qty     INTEGER NOT NULL DEFAULT 1,
  priority    INTEGER NOT NULL DEFAULT 2,
  note        TEXT,
  UNIQUE(project_id, part_id),
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);
CREATE INDEX idx_bom_project ON project_bom(project_id);
CREATE INDEX idx_bom_part    ON project_bom(part_id);
CREATE TABLE project_alloc (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL,
  part_id     INTEGER NOT NULL,
  location    TEXT,
  alloc_qty   INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'reserved',
  note        TEXT,
  updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);
CREATE INDEX idx_alloc_project ON project_alloc(project_id);
CREATE INDEX idx_alloc_part    ON project_alloc(part_id);
CREATE INDEX idx_alloc_loc     ON project_alloc(location);
CREATE TRIGGER trg_alloc_location_check
BEFORE INSERT ON project_alloc
WHEN NEW.location IS NOT NULL AND NEW.location <> ''
BEGIN
  SELECT
    CASE
      WHEN (SELECT COUNT(1) FROM locations WHERE location = NEW.location) = 0
      THEN RAISE(ABORT, 'location 不存在于 locations 表')
    END;
END;
CREATE TRIGGER trg_alloc_location_check_u
BEFORE UPDATE OF location ON project_alloc
WHEN NEW.location IS NOT NULL AND NEW.location <> ''
BEGIN
  SELECT
    CASE
      WHEN (SELECT COUNT(1) FROM locations WHERE location = NEW.location) = 0
      THEN RAISE(ABORT, 'location 不存在于 locations 表')
    END;
END;
CREATE VIEW v_project_material_status AS
WITH
stock_sum AS (
  SELECT part_id, SUM(qty) AS total_stock
  FROM stock
  GROUP BY part_id
),
alloc_sum_all AS (
  SELECT part_id, SUM(CASE WHEN status IN ('reserved','consumed') AND alloc_qty>0 THEN alloc_qty ELSE 0 END) AS reserved_qty
  FROM project_alloc
  GROUP BY part_id
),
alloc_sum_proj AS (
  SELECT project_id, part_id, SUM(CASE WHEN status IN ('reserved','consumed') AND alloc_qty>0 THEN alloc_qty ELSE 0 END) AS reserved_for_project
  FROM project_alloc
  GROUP BY project_id, part_id
)
SELECT
  pr.code AS project_code,
  pr.name AS project_name,
  p.category,
  p.mpn,
  p.name AS part_desc,
  p.package,
  p.params,
  b.req_qty,
  IFNULL(ss.total_stock, 0) AS total_stock,
  IFNULL(aa.reserved_qty, 0) AS reserved_qty_all_projects,
  (IFNULL(ss.total_stock, 0) - IFNULL(aa.reserved_qty, 0)) AS available_stock,
  IFNULL(ap.reserved_for_project, 0) AS reserved_for_project,
  (b.req_qty - IFNULL(ap.reserved_for_project, 0)) AS remaining_to_reserve,
  CASE
    WHEN (IFNULL(ss.total_stock, 0) - IFNULL(aa.reserved_qty, 0)) >= (b.req_qty - IFNULL(ap.reserved_for_project, 0))
      THEN 0
    ELSE (b.req_qty - IFNULL(ap.reserved_for_project, 0)) - (IFNULL(ss.total_stock, 0) - IFNULL(aa.reserved_qty, 0))
  END AS shortage_if_reserve_now
FROM project_bom b
JOIN projects pr ON pr.id = b.project_id
JOIN parts p     ON p.id  = b.part_id
LEFT JOIN stock_sum ss      ON ss.part_id = p.id
LEFT JOIN alloc_sum_all aa  ON aa.part_id = p.id
LEFT JOIN alloc_sum_proj ap ON ap.project_id = pr.id AND ap.part_id = p.id
/* v_project_material_status(project_code,project_name,category,mpn,part_desc,package,params,req_qty,total_stock,reserved_qty_all_projects,available_stock,reserved_for_project,remaining_to_reserve,shortage_if_reserve_now) */;
CREATE VIEW v_project_alloc_detail AS
SELECT
  pr.code AS project_code,
  pr.name AS project_name,
  p.mpn,
  p.name AS part_desc,
  a.location,
  a.alloc_qty,
  a.status,
  a.updated_at,
  a.note
FROM project_alloc a
JOIN projects pr ON pr.id = a.project_id
JOIN parts p     ON p.id  = a.part_id
/* v_project_alloc_detail(project_code,project_name,mpn,part_desc,location,alloc_qty,status,updated_at,note) */;
CREATE TRIGGER trg_alloc_no_overreserve_ins
BEFORE INSERT ON project_alloc
WHEN NEW.alloc_qty > 0
 AND NEW.status IN ('reserved','consumed')
BEGIN
  SELECT
    CASE
      WHEN (
        IFNULL((SELECT SUM(qty) FROM stock WHERE part_id = NEW.part_id), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：全局可用库存不足')
    END;

  SELECT
    CASE
      WHEN (NEW.location IS NOT NULL AND NEW.location <> '')
       AND (
        IFNULL((SELECT SUM(qty) FROM stock
                WHERE part_id = NEW.part_id AND location = NEW.location), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND location = NEW.location
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：该库位可用库存不足')
    END;
END;
CREATE TRIGGER trg_alloc_no_overreserve_upd
BEFORE UPDATE OF part_id, location, alloc_qty, status ON project_alloc
WHEN NEW.alloc_qty > 0
 AND NEW.status IN ('reserved','consumed')
BEGIN
  SELECT
    CASE
      WHEN (
        IFNULL((SELECT SUM(qty) FROM stock WHERE part_id = NEW.part_id), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0
                  AND id <> OLD.id), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：全局可用库存不足（更新被阻止）')
    END;

  SELECT
    CASE
      WHEN (NEW.location IS NOT NULL AND NEW.location <> '')
       AND (
        IFNULL((SELECT SUM(qty) FROM stock
                WHERE part_id = NEW.part_id AND location = NEW.location), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND location = NEW.location
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0
                  AND id <> OLD.id), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：该库位可用库存不足（更新被阻止）')
    END;
END;
