import os
from pathlib import Path
import subprocess


def test_isolated_experimental_identity_and_project_boundaries(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'QISHU_DATA_DIR': str(tmp_path), 'QISHU_EXPERIMENTAL_MULTIUSER': '1',
           'QISHU_ALLOWED_ORIGINS': 'https://testserver', 'DEEPSEEK_API_KEY': 'fake-for-test', 'PYTHONPATH': str(root)}
    result = subprocess.run([str(root / '.venv/bin/python'), str(root / 'tests/collaboration_scenario.py')],
                            cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_50_accounts_10_concurrent_requests_and_edit_conflicts(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'QISHU_DATA_DIR': str(tmp_path), 'QISHU_EXPERIMENTAL_MULTIUSER': '1',
           'QISHU_ALLOWED_ORIGINS': 'https://testserver', 'DEEPSEEK_API_KEY': '', 'PYTHONPATH': str(root)}
    result = subprocess.run([str(root / '.venv/bin/python'), str(root / 'tests/collaboration_load_scenario.py')],
                            cwd=root, env=env, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr


def test_cancel_running_model_results_are_not_saved(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'QISHU_DATA_DIR': str(tmp_path), 'QISHU_EXPERIMENTAL_MULTIUSER': '1',
           'QISHU_ALLOWED_ORIGINS': 'https://testserver', 'DEEPSEEK_API_KEY': 'fake-for-test', 'PYTHONPATH': str(root)}
    result = subprocess.run([str(root / '.venv/bin/python'), str(root / 'tests/cancel_running_scenario.py')],
                            cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_section_edit_queue_revocation_and_recovery(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'QISHU_DATA_DIR': str(tmp_path), 'QISHU_EXPERIMENTAL_MULTIUSER': '1',
           'QISHU_ALLOWED_ORIGINS': 'https://testserver', 'DEEPSEEK_API_KEY': 'fake-for-test', 'PYTHONPATH': str(root)}
    result = subprocess.run([str(root / '.venv/bin/python'), str(root / 'tests/section_edit_scenario.py')],
                            cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_section_edit_conflict_preserves_manual_changes_and_candidate(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'QISHU_DATA_DIR': str(tmp_path), 'QISHU_EXPERIMENTAL_MULTIUSER': '1',
           'QISHU_ALLOWED_ORIGINS': 'https://testserver', 'DEEPSEEK_API_KEY': 'fake-for-test', 'PYTHONPATH': str(root)}
    result = subprocess.run([str(root / '.venv/bin/python'), str(root / 'tests/section_edit_conflict_scenario.py')],
                            cwd=root, env=env, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr


def test_consistency_check_queue_revocation_and_restart(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,'QISHU_DATA_DIR':str(tmp_path),'QISHU_EXPERIMENTAL_MULTIUSER':'1',
         'QISHU_ALLOWED_ORIGINS':'https://testserver','DEEPSEEK_API_KEY':'fake-for-test','PYTHONPATH':str(root)}
    result=subprocess.run([str(root/'.venv/bin/python'),str(root/'tests/consistency_scenario.py')],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_outline_concurrent_versions_permissions_and_restart(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,'QISHU_DATA_DIR':str(tmp_path),'QISHU_EXPERIMENTAL_MULTIUSER':'1',
         'QISHU_ALLOWED_ORIGINS':'https://testserver','DEEPSEEK_API_KEY':'fake-for-test','PYTHONPATH':str(root)}
    result=subprocess.run([str(root/'.venv/bin/python'),str(root/'tests/outline_scenario.py')],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
