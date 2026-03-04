import html
import io

from fastapi.responses import StreamingResponse

from ..models import Inventory, MachineLedger
from ..utils.number_format import dec_fixed_3, dec_trimmed
from ..utils.text import normalized_lower


def build_stock_records_export(rows: list[dict], kind: str) -> StreamingResponse:
    stream = io.StringIO()
    stream.write('<html><head><meta charset="utf-8"></head><body>')
    title = "入库记录" if kind == "in" else "出库记录"
    stream.write('<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;width:100%;">')
    stream.write(f'<tr><th colspan="5" style="text-align:center;font-size:16px;">{html.escape(title)}</th></tr>')
    stream.write('<tr>')
    for col_title in ["序号", "日期", "名称", "数量", "单位"]:
        stream.write(f'<th style="text-align:center;padding:4px 2ch;white-space:nowrap;">{html.escape(col_title)}</th>')
    stream.write('</tr>')

    for idx, row in enumerate(rows, start=1):
        qty_text = dec_trimmed(row.get("total_qty") or "0")
        row_values = [
            idx,
            (row.get("created_at") or "").replace("T", " ")[:10],
            row.get("materials_summary") or "",
            qty_text,
            row.get("unit") or "",
        ]
        stream.write('<tr>')
        for value in row_values:
            text = html.escape(f"{value or ''}")
            stream.write(f'<td style="text-align:center;padding:4px 2ch;white-space:nowrap;">{text}</td>')
        stream.write('</tr>')

    stream.write('</table></body></html>')
    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.ms-excel; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=stock-records.xls"
    return response


def build_inventory_export(rows: list[Inventory]) -> StreamingResponse:
    stream = io.StringIO()
    stream.write('<html><head><meta charset="utf-8"></head><body>')
    stream.write('<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;width:100%;">')
    stream.write('<tr><th colspan="5" style="text-align:center;font-size:16px;">库存台账</th></tr>')
    stream.write('<tr>')
    for title in ["名称", "规格", "库存", "单位", "更新时间"]:
        stream.write(f'<th style="text-align:center;padding:4px 2ch;white-space:nowrap;">{html.escape(title)}</th>')
    stream.write('</tr>')

    for row in rows:
        row_values = [
            row.material.name,
            row.material.spec,
            dec_fixed_3(row.qty),
            row.material.unit,
            row.updated_at.strftime("%Y-%m-%d %H:%M") if row.updated_at else "",
        ]
        stream.write('<tr>')
        for value in row_values:
            text = html.escape(f"{value or ''}")
            stream.write(f'<td style="text-align:center;padding:4px 2ch;white-space:nowrap;">{text}</td>')
        stream.write('</tr>')

    stream.write('</table></body></html>')
    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.ms-excel; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=inventory.xls"
    return response


def build_machine_ledger_export(rows: list[MachineLedger], keyword: str = "") -> StreamingResponse:
    kw = normalized_lower(keyword)
    filtered_rows: list[MachineLedger] = []
    for row in rows:
        if kw and kw not in f"{row.name} {row.spec} {row.remark}".lower():
            continue
        filtered_rows.append(row)

    stream = io.StringIO()
    stream.write('<html><head><meta charset="utf-8"></head><body>')
    stream.write('<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;width:100%;">')
    stream.write('<tr><th colspan="6" style="text-align:center;font-size:16px;">机械台账</th></tr>')
    stream.write('<tr>')
    for title in ["序号", "施工日期", "名称", "规格", "台班", "备注"]:
        stream.write(f'<th style="text-align:center;padding:4px 2ch;white-space:nowrap;">{html.escape(title)}</th>')
    stream.write('</tr>')

    for index, row in enumerate(filtered_rows, start=1):
        row_values = [
            f"{index:02d}",
            row.use_date or "",
            row.name,
            row.spec,
            dec_trimmed(row.shift_count) if row.shift_count is not None else "",
            row.remark,
        ]
        stream.write('<tr>')
        for value in row_values:
            text = html.escape(f"{value or ''}")
            stream.write(f'<td style="text-align:center;padding:4px 2ch;white-space:nowrap;">{text}</td>')
        stream.write('</tr>')

    stream.write('</table></body></html>')

    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.ms-excel; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=machine-ledger.xls"
    return response
