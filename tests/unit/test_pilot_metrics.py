import importlib.util
import json
from pathlib import Path

import pytest
from test_classroom_pilot_check import pilot


def row(state='speaker_selected', phase='speaker_switch', **speaker):
    return {'phase': phase, 'values': {'speaker': {'state': state, **speaker}}, 'errors': {}}


def test_missing_samples_do_not_become_successes():
    rows = [row(), row('ambiguous'), {'phase': 'speaker_switch'}, row('invalid')]
    metrics = pilot.phase_metrics(rows)['speaker_switch']
    assert metrics['speaker_state_samples'] == 2
    assert metrics['speaker_state_missing_samples'] == 2
    assert metrics['selected_fraction'] == .5
    assert metrics['ambiguous_fraction'] == .5


def test_missing_phase_is_unknown_not_zero_success():
    metrics = pilot.phase_metrics([])['remote_only']
    assert metrics['selected_fraction'] is None
    assert metrics['p95_selected_angular_error_degrees'] is None
    assert metrics['total_samples'] == 0


def test_errors_exclude_even_a_leftover_payload():
    record = row()
    record['errors'] = {'speaker': 'HTTP 503'}
    metrics = pilot.phase_metrics([record])['speaker_switch']
    assert metrics['speaker_state_samples'] == 0
    assert metrics['speaker_state_missing_samples'] == 1


def test_numeric_metrics_use_selected_valid_values_only():
    rows = [row(center_x=.3, angular_error_degrees=2),
            row(center_x=.6, angular_error_degrees=10),
            row('ambiguous', center_x=0, angular_error_degrees=99),
            row(center_x=float('nan'), angular_error_degrees=float('inf')),
            row(center_x=True, angular_error_degrees=-1)]
    metrics = pilot.phase_metrics(rows)['speaker_switch']
    assert metrics['selected_center_samples'] == 2
    assert metrics['mean_selected_abs_center_error'] == .15
    assert metrics['selected_angular_error_samples'] == 2
    assert metrics['p95_selected_angular_error_degrees'] == 10
    json.dumps(metrics, allow_nan=False)


def test_nearest_rank_and_phase_isolation():
    rows = [row(angular_error_degrees=i) for i in range(1, 21)]
    rows.append(row('waiting_for_speech', phase='remote_only'))
    metrics = pilot.phase_metrics(rows)
    assert metrics['speaker_switch']['p95_selected_angular_error_degrees'] == 19
    assert metrics['remote_only']['selected_fraction'] == 0
    assert metrics['remote_only']['speaker_state_samples'] == 1


def test_markdown_includes_phase_metrics_and_unknowns(tmp_path):
    report = pilot.make_report([], 600, 1, 'interrupted', 2)
    pilot.write_reports(tmp_path, report)
    text = (tmp_path / 'report.md').read_text()
    assert 'Phase telemetry' in text
    assert '| remote_only | 0 / 0 | N/A' in text
    assert report['schema_version'] == 2


@pytest.fixture
def follow():
    path = Path(__file__).resolve().parents[2] / 'scripts/validate_active_speaker_follow.py'
    spec = importlib.util.spec_from_file_location('follow', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('label', ['Speaker-01', 'Speaker-02', 'Speaker-19'])
def test_follow_accepts_matching_current_label(follow, label):
    assert follow.speaker_drives_tracking(
        {'state': 'speaker_selected', 'speaker_id': label},
        {'state': 'tracking', 'source': 'active_speaker', 'target_id': label},
        {'executed': True, 'last_error': ''},
    )


@pytest.mark.parametrize('change', [
    {'target_id': 'Speaker-01'}, {'source': 'visual'}, {'state': 'lost'},
])
def test_follow_rejects_mismatched_tracking(follow, change):
    tracking = {'state': 'tracking', 'source': 'active_speaker', 'target_id': 'Speaker-02'}
    tracking.update(change)
    assert not follow.speaker_drives_tracking(
        {'state': 'speaker_selected', 'speaker_id': 'Speaker-02'}, tracking,
        {'executed': True, 'last_error': ''},
    )
