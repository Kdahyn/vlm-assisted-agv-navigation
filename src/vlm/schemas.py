"""VLM 응답의 필드, 열거값, 신뢰도와 경로 제한 여부를 검증한다."""
from __future__ import annotations
import math

SCENE_TYPES = {'clear', 'crossing', 'working', 'obstruction', 'hazardous_leak_suspected', 'unknown'}
OCCUPANCY_TYPES = {'none', 'short_term', 'long_term', 'unknown'}
TEMPORAL_TRENDS = {'clear', 'clearing', 'stable', 'expanding', 'unknown'}
RISK_LEVELS = {'low', 'medium', 'high', 'unknown'}
MOTION_ACTIONS = {'KEEP', 'STOP_WAIT', 'REROUTE_REQUEST', 'HOLD_POSITION'}
OPERATOR_ACTIONS = {'NONE', 'NOTIFY', 'ALERT'}
ENUMS = dict(scene_type=SCENE_TYPES, occupancy_type=OCCUPANCY_TYPES,
             temporal_trend=TEMPORAL_TRENDS, risk_level=RISK_LEVELS,
             motion_action=MOTION_ACTIONS, operator_action=OPERATOR_ACTIONS)


class SchemaError(ValueError):
    pass


def validate_vlm_result(data: dict) -> dict:
    if not isinstance(data, dict):
        raise SchemaError('VLM output must be an object')
    data = dict(data)
    # 이전 입력 필드를 motion_action으로 통일한다.
    if 'motion_action' not in data and 'recommended_action' in data:
        data['motion_action'] = data['recommended_action']
    out = {}
    for key, allowed in ENUMS.items():
        if not isinstance(data.get(key), str) or data[key] not in allowed:
            raise SchemaError(f'{key} must be one of {sorted(allowed)}')
        out[key] = data[key]
    confidence = data.get('confidence')
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise SchemaError('confidence must be a finite number in [0, 1]')
    if type(data.get('route_restriction')) is not bool:
        raise SchemaError('route_restriction must be a JSON boolean')
    if not isinstance(data.get('reason'), str) or not data['reason'].strip():
        raise SchemaError('reason must be a nonempty string')
    out.update(confidence=float(confidence), route_restriction=data['route_restriction'],
               reason=data['reason'].strip()[:2000])
    return out


def unknown_result(reason: str) -> dict:
    return dict(scene_type='unknown', occupancy_type='unknown', temporal_trend='unknown',
                risk_level='unknown', motion_action='HOLD_POSITION', operator_action='ALERT',
                route_restriction=True, reason=reason, confidence=0.0)
