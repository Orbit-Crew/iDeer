from app.device_control.receipt_archive import safe_logical_target


def test_receipt_target_matches_nested_file_execution_argument_precedence():
    target = "/workspace/00000000-0000-0000-0000-000000000101/marker.txt"
    assert safe_logical_target({"path": target}) == target
    assert safe_logical_target({"path": "ignored", "arguments": {"path": target}}) == target
    assert safe_logical_target({"path": "ignored", "args": {"path": target}}) == target
    assert safe_logical_target({"arguments": {"path": target}, "args": {"path": "/wrong"}}) == target
    assert safe_logical_target({"arguments": {"path": "C:\\private\\secret.txt"}}).startswith("sha256:")
