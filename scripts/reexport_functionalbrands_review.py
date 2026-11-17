"""Rebuild sample from the sealed example's source rows and existing metadata only."""
from pathlib import Path
from openpyxl import load_workbook
from royalty_research.m13_research_export import write_research_xlsx
ROOT=Path(__file__).resolve().parents[1]
old=load_workbook(ROOT/'examples/M13_Original_FunctionalBrands_16sheet.xlsx',read_only=True,data_only=True)
rows={s.title:[[c.value for c in row] for row in s.iter_rows()] for s in old}
prior=load_workbook(ROOT/'examples/M13_Research_FunctionalBrands_5sheet_v0.13.2.xlsx',read_only=True,data_only=True)
s=prior['01 Royalty Database'];h=[c.value for c in s[7]]
first={}
for values in s.iter_rows(min_row=8,values_only=True):
    r=dict(zip(h,values));did=r['Document ID']
    if did in first:continue
    a={}
    for k,col in [('licensed_ip_nature','Nature of IA'),('licensed_ip_nature_details','IA classification detail'),('sublicensing_rights','Sublicensing rights'),('exclusivity_scope','Exclusivity scope')]:
        if r.get(col) not in (None,'','NOT_ASSESSED'):a[k]=r[col]
    refs={}
    for k,col in [('licensed_ip_nature','IA evidence IDs'),('sublicensing_rights','Sublicensing evidence IDs'),('exclusivity_scope','Exclusivity scope evidence IDs')]:
        if r.get(col):refs[k]=r[col].split('; ')
    a['field_evidence']=refs
    first[did]={'agreement':a}
out=ROOT/'examples/M13_Research_FunctionalBrands_5sheet_v0.13.3.xlsx'
write_research_xlsx(rows,out,first)
print(out)
