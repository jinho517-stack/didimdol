"""사업지구·사업(시설)·항목 목록. config.yaml의 districts × item_templates(+common_items)로 만든다.
통합 비교에 쓰는 사업 유형 추정과 시행주체 구분(지자체/LH/국가)도 여기서 한다."""
import re
from pathlib import Path

import llm


def load(cfg=None):
    cfg = cfg or llm.load_config()
    tpl, common = cfg.get('item_templates', {}), cfg.get('common_items', [])
    items, types = [], {}
    for d in cfg.get('districts', []):
        for fac in d.get('facilities', []):
            types[(d['name'], fac['name'])] = fac['type']
            for it in tpl.get(fac['type'], []) + common:
                items.append({'district': d['name'], 'facility': fac['name'], 'type': fac['type'], 'item': it['item'],
                              'unit': it.get('unit') or '', 'kind': it.get('kind', '')})
    return {
        'default': cfg.get('district') or (cfg.get('districts') or [{'name': ''}])[0]['name'],
        'districts': [d['name'] for d in cfg.get('districts', [])],
        'keys': {d['name']: d.get('key') or d['name'] for d in cfg.get('districts', [])},
        'items': items,
        'types': types,
        'kinds': {it['item']: it['kind'] for it in items if it['kind']},
    }


def items_for(cat, district):
    return [i for i in cat['items'] if i['district'] == district]


def order(cat, district=None):
    """보고서·화면에 쓸 (시설, 항목) 순서."""
    return [(i['facility'], i['item']) for i in cat['items'] if district is None or i['district'] == district]


def guess_district(cat, filename):
    name = Path(filename).name
    for d, key in cat['keys'].items():
        if key and key in name:
            return d
    return cat['default']


def facility_type(cat, district, facility):
    t = cat['types'].get((district, facility))
    if t:
        return t
    if re.search(r'철도|[가-힣]선(\(|$| )|전철|지하철', facility):
        return '철도'
    if '환승' in facility:
        return '환승'
    if re.search(r'버스|BRT|대중교통', facility):
        return '대중교통'
    return '도로'


def entity_class(name):
    """시행주체 문구 → 구분. 예) 가온시 → 지자체(기초), A도 → 지자체(광역), 사업시행자(LH) → LH(사업시행자)."""
    s = (name or '').strip()
    if not s:
        return '미정'
    if re.search(r'LH|사업시행자|토지주택', s):
        return 'LH(사업시행자)'
    if re.search(r'국가철도공단|국토교통부|국토부|공단|국가', s):
        return '국가·공공기관'
    if re.search(r'(특별시|광역시|특별자치시|[가-힣A-Z]도)(\s|$|\()', s + ' '):
        return '지자체(광역)'
    if re.search(r'[가-힣]+(시|군|구)(\s|$|\()', s + ' '):
        return '지자체(기초)'
    return '기타'
