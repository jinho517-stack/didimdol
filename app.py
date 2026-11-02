"""디딤돌 웹앱 (Streamlit).  실행: streamlit run app.py
화면: 📊 대시보드(지구별: 확인 필요 선택 + 사업별 최신값 + 문서 흐름 + 항목 이력) / 🔎 통합 비교(여러 지구 사업 필터)
/ 💬 질문하기(DB 검색 챗봇) / 📂 문서 / 📝 보고서·자료.
원본 문서는 읽기만 하고, DB·자료표·보고서·업로드 사본은 output/ 폴더에 만든다."""
import json
import re
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import catalog
import compare
import db
import draft
import extract
import llm
import query
from resolver import INFORMAL, norm

BASE = Path(__file__).parent
SAMPLE = BASE / 'sample'
UPLOADS = db.OUTPUT / 'uploads'
NAV = ['📊 대시보드', '🔎 통합 비교', '💬 질문하기', '📂 문서', '📝 보고서·자료']
# 지구 구분 색: 기준 팔레트 범주형 순서(파랑·주황·청록 …), 지구 순서대로 고정
DISTRICT_COLOR = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
NO_VERSION = '없음'
METHOD_LABEL = {'충돌 없음': '충돌 없음', '규칙(단계 우선순위)': '규칙: 상위 단계', '규칙(같은 단계에서 최근 일자)': '규칙: 최근 일자',
                '사람 선택': '담당자 선택', '사람 선택 필요': '확인 필요', '공식 문서 없음': '공식 문서 없음'}
# 문서 단계(서열) 색: 기준 팔레트의 파랑 단계 ramp, 비공식은 회색
STAGE_ORDER = ['확정·승인본', '협의결과', '보고', '초안', '비공식']
STAGE_COLOR = ['#104281', '#256abf', '#5598e7', '#86b6ef', '#898781']

st.set_page_config(page_title='디딤돌', page_icon='📑', layout='wide')
cfg = llm.load_config()
CAT = catalog.load(cfg)  # 지구·사업·항목 목록 (config.yaml districts × item_templates)
KINDS = CAT['kinds']  # 문장형 항목: attr / status / issue / plan
DEPT = cfg.get('report', {}).get('dept', '')
HAS_LLM = llm.available(cfg)
con = db.connect()

st.markdown("""<style>
.dd-kpi{border:1px solid rgba(128,128,128,.28);border-radius:10px;padding:10px 14px;margin-bottom:8px}
.dd-kpi .n{font-size:1.8rem;font-weight:700;line-height:1.2}
.dd-kpi .l{font-size:.85rem;opacity:.75}
.dd-kpi.warn{border-color:#fab219;background:rgba(250,178,25,.10)}
.dd-card{border:1px solid rgba(128,128,128,.28);border-radius:12px;padding:12px 16px 8px;margin-bottom:14px}
.dd-card h4{margin:0 0 4px;font-size:1.05rem;padding:0}
.dd-row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;
        border-top:1px solid rgba(128,128,128,.16);gap:10px}
.dd-item{font-size:.92rem}
.dd-change{font-size:.75rem;opacity:.7}
.dd-val{font-size:1.2rem;font-weight:700;text-align:right;white-space:nowrap}
.dd-meta{font-size:.74rem;opacity:.68;text-align:right}
.dd-chip{display:inline-block;font-size:.72rem;font-weight:600;padding:0 7px;border-radius:9px;margin-left:6px;
         border:1px solid #0ca30c;vertical-align:middle}
.dd-chip.warn{border-color:#fab219;background:rgba(250,178,25,.20)}
.dd-chip.ref{border-color:#898781}
.dd-ico-ok{color:#0ca30c}.dd-ico-warn{color:#c98500}
.dd-memo{font-size:.8rem;margin:2px 0 8px;padding:5px 9px;border-radius:8px;background:rgba(137,135,129,.13)}
.dd-status{font-size:.9rem;font-weight:600;margin:0 0 6px}
.dd-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#2a78d6;margin-right:6px;vertical-align:middle}
.dd-text{font-size:.86rem;padding:7px 0;border-top:1px solid rgba(128,128,128,.16);line-height:1.5}
.dd-tl{font-size:.74rem;font-weight:700;opacity:.75;margin-bottom:1px}
.dd-cand{border:1px solid rgba(128,128,128,.3);border-radius:10px;padding:10px 12px;margin-bottom:6px}
.dd-cand .v{font-size:1.6rem;font-weight:700}
.dd-cand .f{font-size:.82rem}.dd-cand .m{font-size:.76rem;opacity:.7}
.rp-paper{background:#fff;color:#111;border:1px solid #c9c9c9;border-radius:6px;padding:26px 30px;
          font-family:'Malgun Gothic','맑은 고딕',sans-serif;line-height:1.75;max-width:900px}
.rp-title{border:2px solid #1c5cab;background:#eef4fc;text-align:center;padding:10px;font-size:1.3rem;font-weight:700}
.rp-title small{display:block;font-size:.75rem;font-weight:400;color:#52514e}
.rp-date{text-align:right;font-size:.88rem;margin:6px 0 10px}
.rp-h{font-weight:700;font-size:1.06rem;margin:14px 0 2px}
.rp-b{padding-left:12px}.rp-s{padding-left:34px;font-size:.9rem;color:#333}.rp-act{font-weight:600}
.rp-cap{text-align:center;font-weight:600;margin:6px 0 2px;font-size:.88rem}
.rp-tw{overflow-x:auto}.rp-t{border-collapse:collapse;width:100%;font-size:.8rem;margin-bottom:6px}
.rp-t th,.rp-t td{border:1px solid #999;padding:3px 6px;text-align:center}.rp-t th{background:#efefec}
.rp-note{font-size:.8rem;margin-top:14px;color:#444}
</style>""", unsafe_allow_html=True)


def flash(msg):
    st.session_state['flash'] = msg


def show_flash():
    if msg := st.session_state.pop('flash', None):
        st.success(msg)


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def fmt(vs):
    if not vs:
        return '(없음)'
    v, s = vs
    return f"{'—' if v is None else v} [{s}]"


def kpi(col, n, label, warn=False):
    col.markdown(f'<div class="dd-kpi{" warn" if warn else ""}"><div class="n">{n}</div>'
                 f'<div class="l">{label}</div></div>', unsafe_allow_html=True)


def ordered(facts):
    rank = {k: i for i, k in enumerate(catalog.order(CAT))}
    return sorted(facts, key=lambda f: (rank.get((f['facility'], f['item']), 999), f['facility'], f['item']))


def district_options():
    present = db.districts(con)
    return [d for d in CAT['districts'] if d in present] + [d for d in present if d not in CAT['districts']] \
        or CAT['districts']


def district_picker():
    """대시보드·보고서에서 볼 사업지구. 화면 사이를 오가도 같은 지구를 유지한다."""
    opts = district_options()
    if st.session_state.get('district') not in opts:
        st.session_state['district'] = CAT['default'] if CAT['default'] in opts else opts[0]
    return st.selectbox('사업지구', opts, key='district')


# ---------------- 📂 문서 ----------------
def doc_table(docs, with_count=False):
    st.dataframe(pd.DataFrame([{'문서ID': d['doc_id'], '지구': d.get('district') or '', '단계': d['stage'],
                                '일자': d['date'], '버전 종류': d.get('version_kind') or NO_VERSION, '형식': d['format'],
                                **({'후보 수': d['n_cand']} if with_count else {}), '파일명': d['file']}
                               for d in docs]), hide_index=True, width='stretch')


def doc_meta_form(registered):
    """문서 하나를 골라 지구·단계·일자·버전을 고치고, 전체 후보로 다시 판정한다."""
    by_id = {d['doc_id']: d for d in registered}
    versions = [NO_VERSION] + extract.VERSIONS[1:]
    sel = st.selectbox('수정할 문서', list(by_id), format_func=lambda i: f"{i}  {by_id[i]['file']}")
    d = by_id[sel]
    tag = f"{sel}_{d['district']}_{d['stage']}_{d['date']}_{d['version_kind']}"  # DB 값이 바뀌면 입력칸도 새 값으로
    try:
        cur_date = datetime.strptime(d['date'], '%Y-%m-%d').date()
    except ValueError:
        cur_date = datetime.now().date()
    dists = list(dict.fromkeys(CAT['districts'] + [d['district']]))
    c0, c1, c2, c3, c4 = st.columns(5, vertical_alignment='bottom')
    dist = c0.selectbox('지구', dists, key=f'ds_{tag}', index=dists.index(d['district']))
    stage = c1.selectbox('단계', extract.STAGES, key=f'st_{tag}', help='확정·승인본 > 협의결과 > 보고 > 초안. 비공식은 판정에 쓰지 않음',
                         index=extract.STAGES.index(d['stage']) if d['stage'] in extract.STAGES else 2)
    new_date = c2.date_input('일자', cur_date, key=f'dt_{tag}', format='YYYY-MM-DD')
    ver = c3.selectbox('버전 종류', versions, key=f'vk_{tag}', help='같은 단계·같은 일자일 때 최종 > 변경안 > 원안',
                       index=versions.index(d['version_kind'] or NO_VERSION))
    if c4.button('저장하고 다시 판정', type='primary'):
        def snap():
            return {(f['district'], f['facility'], f['item']): (f['value'], f['status']) for f in db.facts(con)}
        before = snap()
        db.update_source_meta(con, sel, stage, new_date.isoformat(), '' if ver == NO_VERSION else ver, dist)
        db.recompute(con, CAT['default'])
        after = snap()
        changed = [f"{k[0]} {k[1]} / {k[2]}: {fmt(before.get(k))} → {fmt(after.get(k))}"
                   for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
        flash(f"{sel} 수정 → 지구 {dist}, 단계 {stage}, 일자 {new_date.isoformat()}, 버전 {ver}. 다시 판정했습니다.\n\n" +
              ('바뀐 항목:\n' + '\n'.join(f'- {c}' for c in changed[:20]) +
               (f'\n- 외 {len(changed) - 20}건' if len(changed) > 20 else '') if changed else '바뀐 항목 없음'))
        st.rerun()


def page_docs():
    st.header('📂 문서')
    st.caption('문서를 넣고 "추출 시작"을 누르면 항목별 최신값을 판정해 대시보드에 보여 줍니다. 원본 문서는 읽기만 합니다.')
    modes = ['샘플 모드 (API 키 불필요)'] + (['실제 추출 (LLM)'] if HAS_LLM else [])
    mode = st.radio('추출 방식', modes, horizontal=True, index=len(modes) - 1)
    if not HAS_LLM:
        st.info(f"환경변수 `{cfg.get('llm', {}).get('api_key_env')}`가 없어 샘플 모드로 동작합니다. "
                'sample/의 A01 추출 결과 예시(CSV)로 판정 이후 흐름을 그대로 실행합니다.')

    if mode.startswith('샘플'):
        c1, c2 = st.columns(2)
        extra = c1.checkbox('누리마루 현안 문서 7개 포함 (sample/extra)', value=True,
                            help='지자체 반대·협의 지연, 노선별 현안·향후계획·시행주체. 끄면 정답표 기준 기본 11개만 씁니다.')
        other = c2.checkbox('다른 지구 문서 8개 포함 (sample/other: 한빛·솔내지구)', value=True,
                            help='통합 비교·질문하기용 가상 지구. 누리마루 판정 결과에는 영향이 없습니다.')
        docs, cands = extract.load_sample(SAMPLE, extra, other, CAT['default'])
        n_d = len({d['district'] for d in docs})
        st.write(f'모의 문서 {len(docs)}개, 사업지구 {n_d}곳 (합성 데이터)')
        doc_table(docs)
        if st.button('추출 시작', type='primary'):
            db.reset(con)  # 샘플 모드는 DB를 새로 만든다
            for d in docs:
                db.save_document(con, d, [c for c in cands if c['doc_id'] == d['doc_id']])
            db.recompute(con, CAT['default'])
            flash(f'샘플 추출 결과 {len(cands)}건을 불러와 지구별로 최신값을 판정했습니다.')
            st.session_state['goto'] = NAV[0]
            st.rerun()
    else:
        src = st.radio('문서 가져오기', ['폴더 경로', '파일 선택(여러 개)'], horizontal=True)
        paths = []
        if src == '폴더 경로':
            folder = st.text_input('폴더 경로', str(SAMPLE))
            if folder and Path(folder).is_dir():
                paths = extract.list_folder(folder)
            elif folder:
                st.warning('폴더를 찾을 수 없습니다.')
        else:
            files = st.file_uploader('문서 선택', type=[e[1:] for e in extract.FORMATS], accept_multiple_files=True)
            UPLOADS.mkdir(parents=True, exist_ok=True)
            for f in files or []:  # 업로드 사본은 output/uploads에만 저장
                p = UPLOADS / f.name
                if not p.exists() or p.stat().st_size != f.size:
                    p.write_bytes(f.getvalue())
                paths.append(p)
        if paths:
            docs = extract.describe(paths, db.next_doc_num(con), CAT)
            for d in docs:  # 이미 등록된 파일은 같은 문서ID로 교체
                d['doc_id'] = db.doc_id_for_file(con, d['file']) or d['doc_id']
            st.write(f'문서 {len(docs)}개. 지구·단계·일자는 파일명으로 추정한 값이며, 추출 후 아래에서 고칠 수 있습니다.')
            doc_table(docs)
            if st.button('추출 시작', type='primary'):
                run_extraction(docs)
                st.session_state['goto'] = NAV[0]
                st.rerun()

    registered = db.sources(con)
    if not registered:
        show_flash()
        return
    st.subheader('등록된 문서')
    doc_table(registered, with_count=True)
    with st.container(border=True):
        st.markdown('**문서 지구·단계·일자·버전 수정** — 저장하면 전체 후보로 다시 판정합니다.')
        doc_meta_form(registered)
        show_flash()
    if st.button('DB 초기화'):
        db.reset(con)
        flash('DB를 비웠습니다. (원본 문서는 그대로입니다)')
        st.rerun()


def run_extraction(docs):
    bar = st.progress(0.0, text='추출 중...')
    errors, notes, n = [], [], 0
    for i, d in enumerate(docs, 1):
        bar.progress((i - 1) / len(docs), text=f'{d["file"]} 추출 중 ({i}/{len(docs)})')
        try:
            cands, meta = extract.extract_candidates(d, catalog.items_for(CAT, d['district']), cfg)
            db.save_document(con, d, cands)
            n += len(cands)
            if meta.get('stage') and meta['stage'] != d['stage']:
                notes.append(f"{d['doc_id']} {d['file']}: AI는 단계를 '{meta['stage']}'로 봄 (파일명 추정 '{d['stage']}' 사용)")
        except Exception as e:
            errors.append(f"{d['file']}: {e}")
    bar.progress(1.0, text='완료')
    db.recompute(con, CAT['default'])
    msg = f'문서 {len(docs) - len(errors)}개에서 후보 {n}건을 추출해 최신값을 판정했습니다.'
    msg += ''.join(f'\n\n⚠ {m}' for m in errors + notes)
    flash(msg)


# ---------------- 📊 대시보드 ----------------
def page_dashboard():
    if not db.facts(con):
        st.header('📊 대시보드')
        st.info('아직 판정한 문서가 없습니다. 📂 문서 화면에서 "추출 시작"을 누르세요.')
        return
    district = district_picker()
    facts = ordered(db.facts(con, district=district))
    sources = db.sources(con, district)
    cands = db.load_candidates(con, district)
    if not facts:
        st.info(f'{district} 문서가 없습니다.')
        return
    by_key = {}
    for c in cands:
        by_key.setdefault((c['facility'], c['item']), []).append(c)
    dates = sorted(s['date'] for s in sources if s['date'])
    st.header(f'📊 {district} 광역교통 최신값 대시보드')
    st.caption(f"문서 {len(sources)}건 기준 ({dates[0]} ~ {dates[-1]}) · 값은 규칙(문서 단계 > 최근 일자 > 버전)으로 판정, "
               'AI는 값을 정하지 않음')
    show_flash()

    conf = [f for f in facts if f['status'] == '미확정(충돌)']
    informal = {(f['facility'], f['item']): [c for c in by_key.get((f['facility'], f['item']), [])
                                             if c['stage'] in INFORMAL and
                                             (f['value'] is None or norm(c['value']) != norm(f['value']))]
                for f in facts}
    n_ref = sum(len(v) for v in informal.values())
    c = st.columns(5)
    kpi(c[0], len(sources), '문서')
    kpi(c[1], len(facts), '항목')
    kpi(c[2], sum(f['status'] == '확정' for f in facts), '✔ 확정')
    kpi(c[3], len(conf), '⚠ 확인 필요', warn=bool(conf))
    kpi(c[4], n_ref, 'ⓘ 비공식 참고')

    # 확인 필요: 대시보드에서 바로 선택
    for f in conf:
        conflict_card(f)
    if not conf:
        st.success('✔ 모든 항목이 확정되었습니다. 문서 간 값이 충돌하는 항목이 없습니다.')

    st.subheader('사업별 최신값')
    by_fac = {}
    for f in facts:
        by_fac.setdefault(f['facility'], []).append(f)
    cols = st.columns(2)
    for i, (fac, fs) in enumerate(by_fac.items()):
        cols[i % 2].markdown(facility_card(fac, fs, by_key, informal), unsafe_allow_html=True)

    st.subheader('문서 흐름')
    st.caption('문서 단계(위로 갈수록 우선)와 일자. 같은 단계면 오른쪽(최근) 문서가 이깁니다. 비공식은 판정에 쓰지 않습니다.')
    st.altair_chart(timeline_chart(sources), width='stretch')

    st.subheader('항목 이력 보기')
    labels = {f"{f['facility']} / {f['item']}": f for f in facts}
    pick = st.selectbox('항목', list(labels), label_visibility='collapsed')
    item_history(labels[pick], by_key.get((labels[pick]['facility'], labels[pick]['item']), []))

    with st.expander('전체 표로 보기'):
        df = pd.DataFrame([query.to_row(f) for f in facts])
        st.dataframe(df, hide_index=True, width='stretch')
        st.download_button('CSV 내려받기', df.to_csv(index=False).encode('utf-8-sig'), '최신값표.csv', 'text/csv')

    ch = db.choices(con, district)
    if ch:
        with st.expander(f'담당자 선택 기록 ({len(ch)}건)'):
            st.dataframe(pd.DataFrame([{
                '시설': c['facility'], '항목': c['item'], '선택값': c['value'], '선택자': c['chooser'],
                '선택일': c['chosen_at'], '상태': '적용 중' if c['active'] else '이력 보관(상위 문서 반영)',
                '후보': ' / '.join(f"{x['value']}{x['unit']}({x['doc_id']})" for x in json.loads(c['candidates'] or '[]'))}
                for c in ch]), hide_index=True, width='stretch')


def conflict_card(f):
    tops = json.loads(f['conflict_candidates'] or '[]')
    with st.container(border=True):
        st.markdown(f"#### ⚠ 확인 필요 · {f['facility']} / {f['item']}")
        same = tops[0] if tops else {}
        st.caption(f"같은 단계({same.get('stage', '')})·같은 일자({same.get('date', '')}) 문서끼리 값이 달라 규칙으로 정할 수 없습니다. "
                   '원문을 대조해 맞는 값을 고르세요.'
                   + (f" 지금은 이전 확정값 {f['value']}{f['unit']}을 유지하고 있습니다." if f['value'] is not None else ''))
        who = st.text_input('선택자', '담당자', key=f"who{f['id']}")
        cols = st.columns(max(len(tops), 1))
        for i, c in enumerate(tops):
            with cols[i]:
                st.markdown(f'<div class="dd-cand"><div class="v">{esc(draft.fmt_value(c["value"], c["unit"]))}</div>'
                            f'<div class="f">{esc(c["file"])}</div>'
                            f'<div class="m">{esc(c["doc_id"])} · {esc(c["stage"])} · {esc(c["date"])} · {esc(c["location"])}</div>'
                            '</div>', unsafe_allow_html=True)
                if st.button(f"{draft.fmt_value(c['value'], c['unit'])}(으)로 확정", key=f"ch{f['id']}_{i}", type='primary',
                             width='stretch'):
                    db.save_choice(con, f['district'], f['facility'], f['item'], c['value'], who or '담당자')
                    flash(f"{f['facility']} / {f['item']}: {draft.fmt_value(c['value'], c['unit'])} 확정. 선택 기록을 저장했습니다.")
                    st.rerun()


def facility_card(fac, fs, by_key, informal):
    rows, head, texts = [], '', []
    for f in fs:
        kind = KINDS.get(f['item'])
        meta = f"{f['source_doc']} · {f['doc_stage']} · {f['doc_date']}" if f['source_doc'] else ''
        memos = ''.join(f'<div class="dd-memo">ⓘ 비공식 메모: {esc(c["value"])} ({esc(c["doc_id"])}) — 반영 안 함</div>'
                        for c in informal.get((f['facility'], f['item']), []))
        if kind == 'status':  # 추진상태는 사업명 아래 한 줄로
            v = '확인 필요' if f['status'] == '미확정(충돌)' else (f['value'] or '—')
            head = (f'<div class="dd-status"><span class="dd-dot"></span>{esc(v)}'
                    f'<span class="dd-meta"> &nbsp;{esc(meta)}</span></div>{memos}')
            continue
        if kind in ('issue', 'plan'):  # 현안·향후계획은 문장으로
            v = '문서 간 내용이 달라 확인 필요' if f['status'] == '미확정(충돌)' else (f['value'] or '—')
            texts.append(f'<div class="dd-text"><div class="dd-tl">{"⚑ 현안" if kind == "issue" else "→ 향후계획"}</div>'
                         f'<div>{esc(v)}</div><div class="dd-meta" style="text-align:left">{esc(meta)}</div></div>{memos}')
            continue
        if f['status'] == '미확정(충돌)':
            val = '확인 필요'
            chip = '<span class="dd-chip warn"><span class="dd-ico-warn">⚠</span> 확인 필요</span>'
        elif f['status'] == '참고':
            val = '—'
            chip = '<span class="dd-chip ref">ⓘ 공식 문서 없음</span>'
        else:
            val = draft.fmt_value(f['value'], f['unit'])
            chip = f'<span class="dd-chip"><span class="dd-ico-ok">✔</span> {METHOD_LABEL.get(f["method"], f["method"])}</span>'
        off = sorted((c for c in by_key.get((f['facility'], f['item']), []) if c['stage'] not in INFORMAL),
                     key=lambda c: (c['date'], c['doc_id']))
        change = ''
        if off and f['value'] is not None and norm(off[0]['value']) != norm(f['value']):
            change = f"처음 {draft.fmt_value(off[0]['value'], f['unit'])} ({off[0]['doc_id']}) → 변경"
        rows.append(f'<div class="dd-row"><div><div class="dd-item">{esc(f["item"])}</div>'
                    f'<div class="dd-change">{esc(change)}</div></div>'
                    f'<div><div class="dd-val">{esc(val)}{chip}</div><div class="dd-meta">{esc(meta)}</div></div></div>')
        for c in informal.get((f['facility'], f['item']), []):
            rows.append(f'<div class="dd-memo">ⓘ 비공식 메모 {esc(draft.fmt_value(c["value"], f["unit"] or c["unit"]))} '
                        f'({esc(c["doc_id"])} {esc(c["file"])}) — 반영 안 함</div>')
    return f'<div class="dd-card"><h4>{esc(fac)}</h4>{head}{"".join(rows)}{"".join(texts)}</div>'


def stage_scale():
    return alt.Scale(domain=STAGE_ORDER, range=STAGE_COLOR)


def timeline_chart(sources):
    df = pd.DataFrame([{'문서': s['doc_id'], '파일': s['file'], '단계': s['stage'], '일자': s['date'],
                        '후보 수': s['n_cand']} for s in sources])
    df['일자'] = pd.to_datetime(df['일자'], errors='coerce')
    base = alt.Chart(df).encode(
        x=alt.X('일자:T', title=None, axis=alt.Axis(format='%m/%d', grid=False)),
        y=alt.Y('단계:N', sort=STAGE_ORDER, title=None, scale=alt.Scale(domain=STAGE_ORDER)),
        tooltip=['문서', '파일', '단계', alt.Tooltip('일자:T', format='%Y-%m-%d'), '후보 수'])
    pts = base.mark_circle(size=170, opacity=1, stroke='white', strokeWidth=2).encode(
        color=alt.Color('단계:N', scale=stage_scale(), legend=None))
    # 같은 날짜·같은 단계 문서는 이름표를 하나로 묶어 겹치지 않게 한다
    lab = df.dropna(subset=['일자']).groupby(['일자', '단계'], as_index=False)['문서'].agg('·'.join)
    lbl = alt.Chart(lab).mark_text(dy=-14, fontSize=11).encode(
        x='일자:T', y=alt.Y('단계:N', sort=STAGE_ORDER, scale=alt.Scale(domain=STAGE_ORDER)), text='문서')
    return (pts + lbl).properties(height=230)


def to_number(v):
    s = str(v).replace(',', '').strip()
    m = re.fullmatch(r'(\d{4})\.(\d{1,2})', s)
    if m and 1 <= int(m.group(2)) <= 12:  # 2031.6 → 2031년 6월
        return int(m.group(1)) + (int(m.group(2)) - 1) / 12
    try:
        return float(s)
    except ValueError:
        return None


def item_history(f, cs):
    is_time = f['unit'] == '' and any(re.fullmatch(r'\d{4}\.\d{1,2}', str(c['value'])) for c in cs)
    rows = [{'문서': c['doc_id'], '파일': c['file'], '단계': c['stage'], '일자': c['date'],
             '값': draft.fmt_value(c['value'], c['unit']), 'y': to_number(c['value']),
             '최신값 근거': '예' if c['doc_id'] == f['source_doc'] else ''} for c in cs]
    df = pd.DataFrame(rows)
    left, right = st.columns([3, 2])
    plot = df.dropna(subset=['y'])
    with left:
        if not plot.empty:
            plot = plot.assign(일자=pd.to_datetime(plot['일자']))
            ytitle = '시기(연)' if is_time else (f['unit'] or '값')
            base = alt.Chart(plot).encode(
                x=alt.X('일자:T', title=None, axis=alt.Axis(format='%m/%d', grid=False)),
                y=alt.Y('y:Q', title=ytitle, scale=alt.Scale(zero=False), axis=alt.Axis(format='.1f' if is_time else ',')),
                tooltip=['문서', '파일', '단계', '값', alt.Tooltip('일자:T', format='%Y-%m-%d')])
            pts = base.mark_point(size=110, filled=True, opacity=1).encode(
                color=alt.Color('단계:N', scale=stage_scale(), legend=alt.Legend(title='문서 단계', orient='bottom')),
                shape=alt.condition(alt.datum['단계'] == '비공식', alt.value('triangle'), alt.value('circle')))
            layers = [pts]
            cur = to_number(f['value']) if f['value'] is not None else None
            if cur is not None:
                layers.append(alt.Chart(pd.DataFrame({'y': [cur]})).mark_rule(strokeDash=[4, 3], color='#52514e')
                              .encode(y='y:Q'))
            st.altair_chart(alt.layer(*layers).properties(height=240), width='stretch')
            st.caption('점선 = 현재 최신값. ▲ = 비공식(반영 안 함).')
        st.dataframe(df.drop(columns=['y']), hide_index=True, width='stretch')
    with right:
        status = {'미확정(충돌)': '⚠ 확인 필요', '확정': '✔ 확정', '참고': 'ⓘ 참고'}.get(f['status'], f['status'])
        st.metric(f"{f['facility']} / {f['item']}", draft.fmt_value(f['value'], f['unit']) if f['value'] is not None else '미확정',
                  help=f['note'] or None)
        st.markdown(f"**{status}** · {METHOD_LABEL.get(f['method'], f['method'])}")
        if f['source_doc']:
            st.caption(f"근거: {f['source_doc']} {f['source_file']} ({f['source_loc']})")
        hs = db.history(con, f['id'])
        if hs:
            st.markdown('**변경 이력**')
            for h in hs:
                prev = h['prev_value'] or '(처음)'
                st.markdown(f"- {prev} → **{h['new_value'] or '—'}**  \n  <small>{esc(h['kind'])} · {esc(h['reason'])}</small>",
                            unsafe_allow_html=True)


# ---------------- 📝 보고서·자료 ----------------
def page_report():
    st.header('📝 보고서·자료')
    if not db.facts(con):
        st.info('먼저 📂 문서 화면에서 "추출 시작"을 누르세요.')
        return
    district = district_picker()
    facts = ordered(db.facts(con, district=district))
    st.caption('양식을 고르면 목차가 미리 체크됩니다. 목차를 켜고 끄면 체크한 목차만으로 초안을 만듭니다. '
               '숫자는 모두 DB 최신값입니다.')

    preset = st.radio('양식', list(draft.PRESETS), horizontal=True, key='rp_preset')
    tail, defaults = draft.PRESETS[preset]
    c1, c2 = st.columns([3, 2])
    title = c1.text_input('보고서 제목', f'{district} {tail}', key=f'rp_title_{preset}_{district}')
    dept = c2.text_input('작성 부서', DEPT, key='rp_dept')
    facs = list(dict.fromkeys(f['facility'] for f in facts))
    pick_facs = st.multiselect('대상 사업', facs, default=facs, key=f'rp_facs_{district}')
    show_basis = st.checkbox('근거 표시(검토용)', value=False, key='rp_basis',
                             help='켜면 값마다 근거 문서·문서ID·판정 설명을 붙입니다. 보고용은 끈 상태로 쓰세요.')

    st.markdown('**목차** (체크한 목차만 보고서에 들어갑니다)')
    cols = st.columns(3)
    chosen = []
    for i, sec in enumerate(draft.SECTIONS):
        ai = sec == '종합 의견(AI)'
        on = cols[i % 3].checkbox(sec, value=sec in defaults and not (ai and not HAS_LLM), key=f'rp_{preset}_{sec}',
                                  help=draft.SECTION_HELP[sec] + ('' if not ai or HAS_LLM else ' — API 키가 없어 사용할 수 없음'),
                                  disabled=ai and not HAS_LLM)
        if on:
            chosen.append(sec)
    extra = {}
    hints = {'주요 현안': '(사업비) 철도 사업비 증액분 분담 협의 필요\n⇒ (대응방안) 관계기관 협의 착수',
             '향후 계획': '(협의) 제21차 실무협의체에서 개통 목표 재확인\n- 11월 중 개최 예정'}
    for sec in ('주요 현안', '향후 계획'):
        if sec in chosen:
            extra[sec] = st.text_area(f'{sec} 직접 입력 (선택)', key=f'rp_extra_{sec}', height=90,
                                      placeholder=f'한 줄에 하나. "(핵심어) 내용", "- 세부", "⇒ 조치"\n예)\n{hints[sec]}',
                                      help='자동으로 만든 문장 뒤에 덧붙습니다. 문서에 없는 계획·현안을 담당자가 적는 칸입니다.')
    if not chosen:
        st.warning('목차를 하나 이상 체크하세요.')
    if st.button('보고서 초안 만들기', type='primary', disabled=not chosen or not pick_facs):
        sel = [f for f in facts if f['facility'] in pick_facs]
        blocks = draft.build(sel, db.load_candidates(con, district), db.sources(con, district), db.choices(con, district),
                             title, district, dept, chosen, extra, HAS_LLM, cfg, order=catalog.order(CAT, district),
                             kinds=KINDS, show_basis=show_basis)
        st.session_state['report'] = {'blocks': blocks, 'facts': sel, 'sections': chosen, 'district': district,
                                      'stamp': datetime.now().strftime('%Y%m%d_%H%M%S')}
    rep = st.session_state.get('report')
    if not rep or rep.get('district') != district:
        return
    blocks = rep['blocks']
    title = next(b[1] for b in blocks if b[0] == 'title')
    safe = re.sub(r'[\\/:*?"<>|]', '_', title)
    st.divider()
    st.caption(f"목차: {' · '.join(rep['sections'])} · 대상 {len({f['facility'] for f in rep['facts']})}개 사업, "
               f"{len(rep['facts'])}개 항목")
    if any(f['status'] == '미확정(충돌)' for f in rep['facts']):
        st.warning('확인 필요 항목이 있습니다. 대시보드에서 확정한 뒤 다시 만들면 보고서에 반영됩니다.')
    d1, d2, d3 = st.columns(3)
    files = [('한글(hwpx) 내려받기', f"{safe}_{rep['stamp']}.hwpx", lambda: draft.to_hwpx(blocks), 'application/octet-stream', d1),
             ('워드(docx) 내려받기', f"{safe}_{rep['stamp']}.docx", lambda: draft.to_docx(blocks),
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document', d2),
             ('자료표 엑셀 내려받기', f"자료표_{rep['stamp']}.xlsx",
              lambda: query.to_excel([query.to_row(f) for f in rep['facts']], title, '대상 사업 선택', db.sources(con, district)),
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', d3)]
    for label, name, make, mime, col in files:
        data = make()
        if col.download_button(label, data, file_name=name, mime=mime, width='stretch'):
            (db.OUTPUT / name).write_bytes(data)
    st.markdown(draft.to_html(blocks), unsafe_allow_html=True)
    with st.expander('자료표(표로 보기)'):
        st.dataframe(pd.DataFrame([query.to_row(f) for f in rep['facts']]), hide_index=True, width='stretch')


# ---------------- 🔎 통합 비교 ----------------
SHOW_COLS = ['지구', '사업명', '유형', '사업비(억원)', '비용 구분', '연장(km)', '시기', '시행주체', '주체 구분', '추진상태', '현안']


NUM_COLS = {'사업비(억원)': st.column_config.NumberColumn(format='%,.0f'), '연장(km)': st.column_config.NumberColumn(format='%.1f')}


def district_scale(names):
    domain = [d for d in CAT['districts'] if d in names] + [d for d in names if d not in CAT['districts']]
    order = {d: i for i, d in enumerate(CAT['districts'] + [d for d in names if d not in CAT['districts']])}
    return alt.Scale(domain=domain, range=[DISTRICT_COLOR[order[d] % len(DISTRICT_COLOR)] for d in domain])


def project_table(rows):
    df = pd.DataFrame(rows)
    return df[[c for c in SHOW_COLS if c in df.columns]] if not df.empty else df


def page_compare():
    st.header('🔎 사업지구 통합 비교')
    facts = db.facts(con)
    if not facts:
        st.info('먼저 📂 문서 화면에서 "추출 시작"을 누르세요. (샘플 모드에서 "다른 지구 문서 포함"을 켜면 3개 지구를 비교합니다)')
        return
    rows = compare.projects(facts, CAT)
    st.caption('여러 사업지구의 광역교통 사업을 같은 기준으로 모아 봅니다. 값은 지구별로 판정한 DB 최신값입니다. '
               '유형·시행주체 구분을 비워 두면 전체입니다.')
    dists = list(dict.fromkeys(r['지구'] for r in rows))
    c1, c2, c3 = st.columns(3)
    pick_d = c1.multiselect('사업지구', dists, default=dists, key='cmp_d')
    pick_t = c2.multiselect('사업 유형', compare.TYPES, key='cmp_t', placeholder='전체')
    ents = [e for e in compare.ENTITY if any(r['주체 구분'] == e for r in rows)]
    pick_e = c3.multiselect('시행주체 구분', ents, key='cmp_e', placeholder='전체')
    top = max([r['사업비(억원)'] for r in rows if r['사업비(억원)'] is not None] or [100])
    top = int(-(-top // 500) * 500)
    c4, c5 = st.columns([3, 2])
    lo, hi = c4.slider('사업비(지원액) 범위, 억원', 0, top, (0, top), step=50, key='cmp_cost')
    kw = c5.text_input('현안·추진상태 검색', key='cmp_kw', placeholder='예: 반대, 지연, 보상 (쉼표로 여러 개)')
    flt = {'districts': pick_d, 'types': pick_t, 'entities': pick_e,
           'keywords': [k.strip() for k in kw.split(',') if k.strip()]}
    if (lo, hi) != (0, top):  # 범위를 움직였을 때만 금액 조건(사업비 없는 사업이 빠지지 않게)
        flt.update(cost_min=lo, cost_max=hi)
    res = compare.run(rows, flt)
    st.caption('조건: ' + compare.describe({k: v for k, v in flt.items() if k != 'districts' or len(v) < len(dists)}))

    c = st.columns(4)
    total = sum(r['사업비(억원)'] or 0 for r in res if r['비용 구분'] == '사업비')
    kpi(c[0], len(res), '사업')
    kpi(c[1], len({r['지구'] for r in res}), '사업지구')
    kpi(c[2], draft.fmt_value(compare._fmt(total), '억원') if total else '—', '사업비 합계')
    kpi(c[3], sum(bool(r['현안']) for r in res), '현안 있는 사업', warn=False)
    if not res:
        st.info('조건에 맞는 사업이 없습니다.')
        return
    plot = pd.DataFrame([r for r in res if r['사업비(억원)'] is not None])
    if not plot.empty:
        st.markdown('**사업비(지원액) 비교**')
        plot['라벨'] = plot['사업비(억원)'].map(lambda v: draft.fmt_value(compare._fmt(v), '억'))
        plot['항목'] = plot['지구'].str.replace('지구', '') + ' · ' + plot['사업명']
        base = alt.Chart(plot).encode(
            y=alt.Y('항목:N', sort='-x', title=None, axis=alt.Axis(labelLimit=260, labelOverlap=False)),
            x=alt.X('사업비(억원):Q', title='억원', axis=alt.Axis(format=',.0f', grid=True, tickCount=6)),
            tooltip=['지구', '사업명', '유형', alt.Tooltip('사업비(억원):Q', format=',.0f'), '비용 구분', '시행주체', '추진상태'])
        bars = base.mark_bar(cornerRadiusEnd=4).encode(
            color=alt.Color('지구:N', scale=district_scale(list(plot['지구'].unique())),
                            legend=alt.Legend(title='사업지구', orient='bottom')))
        text = base.mark_text(align='left', dx=4, fontSize=11).encode(text='라벨')
        st.altair_chart((bars + text).properties(height=alt.Step(26)), width='stretch')
    st.markdown('**사업 목록**')
    df = project_table(res)
    st.dataframe(df, hide_index=True, width='stretch',
                 column_config=NUM_COLS | {'현안': st.column_config.TextColumn(width='large')})
    st.download_button('CSV 내려받기', df.to_csv(index=False).encode('utf-8-sig'), '통합비교.csv', 'text/csv')
    issues = [r for r in res if r['현안']]
    if issues:
        with st.expander(f'현안 모아 보기 ({len(issues)}건)', expanded=True):
            for r in issues:
                st.markdown(f"- **({r['지구']}) {r['사업명']}** · {r['추진상태'] or '상태 미상'}  \n  {r['현안']}"
                            + (f"  \n  → {r['향후계획']}" if r['향후계획'] else ''))


# ---------------- 💬 질문하기 ----------------
EXAMPLES = ['지자체에서 1천억 미만의 유사 도로사업들을 검토해보라고 하는데 다른 사업지구에 이런 사례가 있을까?',
            '개별 광역시설 사업 중에 시행주체(공사주체)가 지자체인 사업의 사례가 있을까?',
            '주민 반대로 협의가 지연되고 있는 사업이 있어?',
            '사업비 5천억 이상 철도사업 알려줘']


def show_answer(m):
    st.markdown(m['text'])
    st.caption(f"검색 조건({m['mode']} 해석): {m['conditions']} → {len(m['rows'])}건")
    for n in m.get('notes') or []:
        st.caption(f'ⓘ {n}')
    if m['rows']:
        st.dataframe(project_table(m['rows']), hide_index=True, width='stretch',
                     column_config=NUM_COLS)


def page_chat():
    st.header('💬 질문하기')
    if not db.facts(con):
        st.info('먼저 📂 문서 화면에서 "추출 시작"을 누르세요.')
        return
    st.caption('질문을 검색 조건(지구·유형·사업비·시행주체·현안 낱말)으로 바꿔 DB에서 바로 찾습니다. 답의 숫자는 모두 DB 값입니다. '
               + ('AI가 질문을 해석하고 답을 씁니다.' if HAS_LLM else 'API 키가 없어 규칙으로 질문을 해석합니다.'))
    c1, c2 = st.columns([2, 1], vertical_alignment='bottom')
    with c1:
        current = district_picker()
    c2.caption('"다른 지구" 질문은 이 지구를 빼고 찾습니다.')
    msgs = st.session_state.setdefault('chat', [])
    if not msgs:
        st.markdown('**예시 질문**')
        for i, q in enumerate(EXAMPLES):
            if st.button(q, key=f'ex{i}'):
                st.session_state['ask'] = q
                st.rerun()
    for m in msgs:
        with st.chat_message(m['role']):
            if m['role'] == 'user':
                st.markdown(m['text'])
            else:
                show_answer(m)
    q = st.chat_input('예: 1천억 미만 도로사업 중 지자체가 시행하는 사례가 있을까?') or st.session_state.pop('ask', None)
    if q:
        msgs.append({'role': 'user', 'text': q})
        with st.spinner('DB 검색 중...'):
            res = compare.answer(q, db.facts(con), CAT, current, HAS_LLM, cfg)
        msgs.append({'role': 'assistant', **res})
        st.rerun()
    if msgs and st.button('대화 지우기'):
        st.session_state['chat'] = []
        st.rerun()


# ---------------- 화면 전환 ----------------
with st.sidebar:
    st.title('디딤돌')
    st.caption(f"사업지구 {len(CAT['districts'])}곳 문서 → 항목별 최신값 DB")
    lc = cfg.get('llm', {})
    st.markdown(f"**모델**: `{lc.get('provider')}` / `{lc.get('model')}`")
    st.markdown('**LLM 연결**: ' + ('사용 가능' if HAS_LLM else '키 없음 → 샘플 모드'))
    st.caption('모델 교체는 config.yaml의 provider·model·base_url·api_key_env를 바꾸면 됩니다. '
               '판정은 LLM 없이 규칙(resolver.py)만으로 합니다.')

if 'goto' in st.session_state:
    st.session_state['nav'] = st.session_state.pop('goto')
elif 'nav' not in st.session_state:
    st.session_state['nav'] = NAV[0] if db.facts(con) else NAV[3]
page = st.radio('화면', NAV, key='nav', horizontal=True, label_visibility='collapsed')
{NAV[0]: page_dashboard, NAV[1]: page_compare, NAV[2]: page_chat, NAV[3]: page_docs, NAV[4]: page_report}[page]()
