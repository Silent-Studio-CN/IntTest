#!/usr/bin/env python3
"""导出工具 — TXT / JSON / SQL / CSV"""

import json
from datetime import datetime
from typing import Any


def _sql_escape(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        return f"'{json.dumps(v, ensure_ascii=False)}'"
    s = str(v)
    return f"'{s.replace(chr(39), chr(39)+chr(39))}'"


def export_txt(data: dict[str, Any], filepath: str):
    lines = [
        "=" * 50,
        "  IntTest 网络测试报告",
        f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 50, "",
    ]
    def _w(section, kv):
        lines.append(f"── {section} ──")
        for k, v in kv.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
    for s, kv in data.items():
        _w(s, kv) if isinstance(kv, dict) else lines.append(f"{s}: {kv}")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def export_json(data: dict[str, Any], filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_sql(data: dict[str, Any], filepath: str, table_name: str = "test_result"):
    flat: dict[str, Any] = {}
    for s, kv in data.items():
        if isinstance(kv, dict):
            for k, v in kv.items():
                flat[f"{s}_{k}"] = v
        else:
            flat[s] = kv
    flat["_timestamp"] = datetime.now().isoformat()
    cols = ", ".join(f'"{k}"' for k in flat)
    vals = ", ".join(_sql_escape(v) for v in flat.values())
    sql = f"INSERT INTO {table_name} ({cols}) VALUES ({vals});\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"-- IntTest Export @ {datetime.now()}\n")
        f.write(sql)


def export_csv(data: dict[str, Any], filepath: str):
    """导出为 CSV（适合 Excel 打开）"""
    import csv
    flat: dict[str, Any] = {}
    for s, kv in data.items():
        if isinstance(kv, dict):
            for k, v in kv.items():
                flat[f"{s}_{k}"] = v
        else:
            flat[s] = kv
    flat["_timestamp"] = datetime.now().isoformat()
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(flat.keys())
        w.writerow([str(v) for v in flat.values()])


def guess_extension(fmt: str) -> str:
    return {"txt": ".txt", "json": ".json", "sql": ".sql", "csv": ".csv"}.get(fmt, ".txt")


def do_export(data: dict, filepath: str, fmt: str):
    fmt = fmt.lower()
    if fmt == "txt":
        export_txt(data, filepath)
    elif fmt == "json":
        export_json(data, filepath)
    elif fmt == "sql":
        export_sql(data, filepath)
    elif fmt == "csv":
        export_csv(data, filepath)
    else:
        export_txt(data, filepath)
