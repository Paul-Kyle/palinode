import pytest
import os
import time
import hashlib
from palinode.core.store import check_freshness
from palinode.core.config import config

def test_fresh_result_marked_valid(tmp_path, monkeypatch):
    """File unchanged since indexing → freshness: valid"""
    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    content = "---\n---\nHello"
    file_path = "test_valid.md"
    full_path = tmp_path / file_path
    full_path.write_text(content)
    
    current_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    results = [{"file_path": file_path, "metadata": {"content_hash": current_hash}}]
    
    checked = check_freshness(results)
    assert checked[0]["freshness"] == "valid"

def test_modified_file_marked_stale(tmp_path, monkeypatch):
    """File changed after indexing → freshness: stale"""
    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    content = "---\n---\nHello"
    file_path = "test_stale.md"
    full_path = tmp_path / file_path
    full_path.write_text(content)
    
    db_hash = "wrong1234567890a"
    results = [{"file_path": file_path, "metadata": {"content_hash": db_hash}}]
    
    checked = check_freshness(results)
    assert checked[0]["freshness"] == "stale"

def test_missing_hash_marked_unknown(tmp_path, monkeypatch):
    """Old memories without content_hash → freshness: unknown"""
    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    content = "---\n---\nHello"
    file_path = "test_unknown.md"
    full_path = tmp_path / file_path
    full_path.write_text(content)
    
    results = [{"file_path": file_path, "metadata": {}}] # No content_hash
    checked = check_freshness(results)
    assert checked[0]["freshness"] == "unknown"

def test_deleted_file_marked_stale(tmp_path, monkeypatch):
    """Source file deleted → freshness: stale"""
    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    file_path = "test_deleted.md"
    # Do not create file
    results = [{"file_path": file_path, "metadata": {"content_hash": "somehash"}}]
    checked = check_freshness(results)
    assert checked[0]["freshness"] == "stale"

def test_freshness_check_performance(tmp_path, monkeypatch):
    """100 results checked in <50ms (just file reads + hash)"""
    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    
    results = []
    for i in range(100):
        file_path = f"test_perf_{i}.md"
        content = f"Test content {i}"
        (tmp_path / file_path).write_text(content)
        current_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        results.append({"file_path": file_path, "metadata": {"content_hash": current_hash}})
        
    start = time.time()
    checked = check_freshness(results)
    duration = time.time() - start
    
    assert duration < 0.05  # <50ms
    assert len(checked) == 100
    assert all(r["freshness"] == "valid" for r in checked)
