"""A01: 문서 읽기 + LLM으로 항목 후보 추출. 원본 문서는 읽기만 한다(수정·이동·삭제 안 함)."""
import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import llm

FORMATS = {'.pdf': 'PDF', '.docx': '워드', '.xlsx': '엑셀', '.hwpx': '한글', '.txt': '텍스트'}
STAGES = ['확정·승인본', '협의결과', '보고', '초안', '비공식']
VERSIONS = ['', '최종', '변경안', '원안']
MAX_CHARS = 30000


# ---------- 문서 읽기 (표는 행 단위 텍스트로, 위치 표시를 [ ]로 붙임) ----------
def read_pdf(path):
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            out.append(f'[{i}쪽]')
            out.append(page.extract_text() or '')
            for t, table in enumerate(page.extract_tables(), 1):
                for r, row in enumerate(table, 1):
                    out.append(f'[{i}쪽 표{t} {r}행] ' + ' | '.join((c or '').replace('\n', ' ') for c in row))
    return '\n'.join(out)


def read_docx(path):
    import docx
    from docx.table import Table
    d = docx.Document(path)
    out, t = [], 0
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            txt = ''.join(n.text or '' for n in el.iter() if n.tag.endswith('}t'))
            if txt.strip():
                out.append(txt)
        elif tag == 'tbl':
            t += 1
            for r, row in enumerate(Table(el, d).rows, 1):
                cells = []
                for c in row.cells:  # 병합 셀 중복 제거
                    if not cells or cells[-1] != c.text:
                        cells.append(c.text)
                out.append(f'[표{t} {r}행] ' + ' | '.join(x.replace('\n', ' ') for x in cells))
    return '\n'.join(out)


def read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        for r, row in enumerate(ws.iter_rows(values_only=True), 1):
            vals = [str(v) for v in row if v is not None and str(v).strip()]
            if vals:
                out.append(f'[{ws.title} {r}행] ' + ' | '.join(vals))
    wb.close()
    return '\n'.join(out)


def read_hwpx(path):
    """hwpx는 zip. Contents/section*.xml의 <hp:t> 텍스트를 문단(<hp:p>) 단위로 읽는다."""
    lines = []

    def walk(el, buf):
        tag = el.tag.rsplit('}', 1)[-1]
        if tag == 't':
            buf.append(''.join(el.itertext()))
        else:
            for ch in el:
                walk(ch, buf)
        if tag == 'p' and buf:
            line = ''.join(buf).strip()
            if line:
                lines.append(line)
            buf.clear()

    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n))
        for n in names:
            walk(ET.fromstring(z.read(n)), [])
    return '\n'.join(lines)


def read_txt(path):
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'cp949'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode('utf-8', 'replace')
    return '\n'.join(f'[{i}행] {line}' for i, line in enumerate(text.splitlines(), 1))


READERS = {'.pdf': read_pdf, '.docx': read_docx, '.xlsx': read_xlsx, '.hwpx': read_hwpx, '.txt': read_txt}


def read_text(path):
    ext = Path(path).suffix.lower()
    if ext not in READERS:
        raise ValueError(f'지원하지 않는 형식: {ext}')
    return READERS[ext](path)


# ---------- 문서 단위 정보 추정 (업로드 화면에서 사람이 확인·수정) ----------
def guess_meta(filename):
    name = Path(filename).stem
    m = re.match(r'(\d{2})(\d{2})(\d{2})', name)
    date = f'20{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else ''
    if '메모' in name or '비공식' in name:
        stage = '비공식'
    elif any(k in name for k in ('협의결과', '회의결과', '결과 알림', '결과알림', '결과 통보', '회신')):
        stage = '협의결과'
    elif '초안' in name:
        stage = '초안'
    elif any(k in name for k in ('확정', '승인')):
        stage = '확정·승인본'
    else:
        stage = '보고'
    version = ''
    if stage == '보고':
        if '최종' in name:
            version = '최종'
        elif '변경(안)' in name or '변경안' in name:
            version = '변경안'
        elif '(안)' in name:
            version = '원안'
    return {'date': date, 'stage': stage, 'version_kind': version}


def describe(paths, start_num=1, cat=None):
    """파일 목록 → 문서 표(문서ID는 파일명 순으로 D01, D02 ...). cat이 있으면 파일명으로 사업지구도 추정."""
    import catalog
    docs = []
    for i, p in enumerate(sorted(paths, key=lambda x: Path(x).name), start_num):
        p = Path(p)
        docs.append({'doc_id': f'D{i:02d}', 'file': p.name, 'format': FORMATS.get(p.suffix.lower(), p.suffix),
                     'path': str(p), 'district': catalog.guess_district(cat, p.name) if cat else '',
                     **guess_meta(p.name)})
    return docs


def list_folder(folder):
    return sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in FORMATS)


# ---------- 샘플 모드: A01 추출 결과 예시(candidates_sample.csv) ----------
def load_sample(sample_dir, extra=False, other=False, default_district=''):
    """기본 모의문서 11개(candidates_sample.csv). extra=True면 누리마루 현안 문서 7개(extra/),
    other=True면 다른 가상 지구 문서 8개(other/)를 더한다. CSV에 지구 열이 없으면 default_district로 본다."""
    sets = [(Path(sample_dir), 'candidates_sample.csv')]
    if extra:
        sets.append((Path(sample_dir) / 'extra', 'candidates_extra.csv'))
    if other:
        sets.append((Path(sample_dir) / 'other', 'candidates_other.csv'))
    cands = []
    for folder, name in sets:
        with open(folder / name, encoding='utf-8') as f:
            cands += [dict(c, _dir=str(folder), district=c.get('district') or default_district) for c in csv.DictReader(f)]
    docs = {}
    for c in cands:
        p = Path(c.pop('_dir')) / c['file']
        if c['doc_id'] not in docs:
            docs[c['doc_id']] = {'doc_id': c['doc_id'], 'district': c['district'], 'file': c['file'], 'date': c['date'],
                                 'stage': c['stage'], 'version_kind': c['version_kind'],
                                 'format': FORMATS.get(p.suffix.lower(), p.suffix), 'path': str(p)}
    docs = sorted(docs.values(), key=lambda d: (d['date'], d['doc_id']))
    return docs, cands


# ---------- LLM 추출 ----------
SYSTEM = '너는 공공기관 사업 문서에서 지정된 항목의 값만 찾아 옮기는 도구다. 추측하거나 계산하지 않는다.'

PROMPT = """[추출할 항목 목록] (시설 / 항목 / 단위)
{items}

[규칙]
1. 위 목록에 있는 항목만 뽑는다. 문서에 없는 값은 절대 만들지 않는다.
2. 문서에서 찾지 못한 항목은 value를 null로 둔다.
3. 값마다 location(문서 속 위치: 쪽·표·행 또는 문단 제목)을 반드시 적는다. 본문의 [ ] 표시를 활용한다.
4. unit은 항목 목록의 단위로 통일한다. 숫자는 쉼표 없이 쓴다(예: 12,000㎡ → value "12000", unit "㎡"). 단위가 빈 항목(시기·목표)은 문서 표기 그대로(예: "2031.6").
5. 문장형 항목(추진상태·현안·향후계획)은 문서에 적힌 내용만 짧게 옮긴다. 추진상태는 15자 안팎의 상태 표현(예: "협의 지연(○○시 반대)", "실시설계 착수"), 현안·향후계획은 문서 표현을 살린 1~2문장. 문서에 그 시설의 현안·계획이 없으면 null.
6. 문서 단위 정보: stage는 {stages} 중 하나, date는 문서일자(YYYY-MM-DD), version_kind는 "최종", "변경안", "원안", "" 중 하나.

[출력 형식]
{{"stage": "...", "date": "YYYY-MM-DD", "version_kind": "...",
  "facts": [{{"facility": "...", "item": "...", "value": "..." 또는 null, "unit": "...", "location": "..."}}]}}

[문서] 파일명: {file}
{text}"""


def extract_candidates(doc, items, cfg=None, text=None):
    """문서 하나 → (후보 목록, LLM이 판단한 문서 정보). 문서 단계·일자는 업로드 화면의 값을 따른다."""
    text = text if text is not None else read_text(doc['path'])
    item_lines = '\n'.join(f"- {i['facility']} / {i['item']} / {i.get('unit') or '(없음)'}" for i in items)
    prompt = PROMPT.format(items=item_lines, stages=', '.join(STAGES), file=doc['file'], text=text[:MAX_CHARS])
    data = llm.ask_json(prompt, system=SYSTEM, cfg=cfg)
    if isinstance(data, list):
        data = {'facts': data}
    units = {(i['facility'], i['item']): i.get('unit') or '' for i in items}
    out = []
    for f in data.get('facts', []) or []:
        k = (f.get('facility'), f.get('item'))
        v = f.get('value')
        if k not in units or v is None or str(v).strip() in ('', 'null', 'None'):
            continue
        v = str(v).strip()
        if re.fullmatch(r'[\d,]+(\.\d+)?', v):  # 숫자만 쉼표 제거(문장형 값의 쉼표는 그대로)
            v = v.replace(',', '')
        out.append({'doc_id': doc['doc_id'], 'facility': k[0], 'item': k[1],
                    'value': v, 'unit': units[k], 'location': str(f.get('location') or '')})
    meta = {k: data.get(k) for k in ('stage', 'date', 'version_kind')}
    return out, meta
