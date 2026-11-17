"""Optional, styled local XLSX generation using openpyxl.

CSV exports are always available with Python stdlib. XLSX export needs the
optional dependency: ``pip install "royalty-research[xlsx]"`` (openpyxl>=3.1).
It does not invoke a server or a model. Every cell is written as a value
(strings never become formulas); the only formulas are the SEC-only
HYPERLINK cells in the Documents sheet.
"""
from __future__ import annotations

import re
from pathlib import Path

# Characters illegal in XML 1.0 (what openpyxl rejects).
_ILLEGAL=re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_WIDE_TAGS=("Quotation","Description","Condition","Source_URL","Evidence","IDs","Comment","Basis")
HYPERLINK_MAX_URL=255  # Excel's HYPERLINK function argument limit


def _clean(value):
    if isinstance(value,str):
        return _ILLEGAL.sub("[CTRL]",value)
    return value


def write_xlsx(rows: dict, destination):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError("XLSX export needs the optional openpyxl package (pip install openpyxl>=3.1). CSV sheets are available without it.") from exc
    from .m3_export import official_sec_url
    wb=Workbook()
    wb.remove(wb.active)
    fill=PatternFill("solid",start_color="FF17283B",end_color="FF17283B")
    font=Font(bold=True,color="FFFFFFFF")
    align=Alignment(vertical="center")
    for name, matrix in rows.items():
        ws=wb.create_sheet(title=name)
        for r,row in enumerate(matrix,start=1):
            for c,val in enumerate(row,start=1):
                cell=ws.cell(row=r,column=c,value=_clean(val))
                if isinstance(cell.value,str):
                    cell.data_type='s'  # never a formula, even if it starts with = + - @
        ws.freeze_panes="A2"
        ncols=len(matrix[0])
        for c in range(1,ncols+1):
            h=ws.cell(row=1,column=c)
            h.fill=fill;h.font=font;h.alignment=align
        ws.row_dimensions[1].height=27
        for ci,h in enumerate(matrix[0],start=1):
            ws.column_dimensions[get_column_letter(ci)].width=36 if any(t in h for t in _WIDE_TAGS) else 21
        # Only the Documents sheet has clickable HYPERLINK formulas; elsewhere
        # the URL stays a plain string (avoids Excel's hyperlink-count limit).
        if name=="Documents" and "Open_Source" in matrix[0]:
            col=matrix[0].index("Open_Source")+1
            urlcol=matrix[0].index("Source_URL")
            for i,r in enumerate(matrix[1:],start=2):
                url=r[urlcol]
                if official_sec_url(url) and len(url)<=HYPERLINK_MAX_URL and not _ILLEGAL.search(url):
                    safe=url.replace('"','""')
                    cell=ws.cell(row=i,column=col)
                    cell.value=f'=HYPERLINK("{safe}","SEC source")'
                    cell.data_type='f'
    out=Path(destination)
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name("."+out.name+".tmp.xlsx")
    try:
        wb.save(str(tmp))
        if not tmp.exists() or tmp.stat().st_size<1000:
            raise RuntimeError("XLSX exporter produced no valid XLSX bytes")
        tmp.replace(out)
    finally:
        if tmp.exists():tmp.unlink()
    return str(out)
