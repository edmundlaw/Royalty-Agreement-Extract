"""Generate labelled two-document combined sample from bundled historical test fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
from royalty_research.storage import read_json
from royalty_research.m3_workspace import init,register_map,register_extraction
from royalty_research.m3_export import build_rows
from royalty_research.m13_research_export import write_research_xlsx
ROOT=Path(__file__).resolve().parents[1]
readings={}
with TemporaryDirectory() as td:
    init(td)
    for name in ('MarketFinders','Qualigen'):
        p=ROOT/'tests/fixtures/m12_saved'
        m=read_json(p/(name+'_map.json'));e=read_json(p/(name+'_extraction.json'))
        register_map(td,m);register_extraction(td,m['document_id'],e,select=True)
        readings[m['document_id']]=e
    rows=build_rows(td)
    out=ROOT/'examples/M13_v0.13.5_combined_HISTORICAL_TEST_DATA.xlsx'
    write_research_xlsx(rows,out,readings)
    print(out)
