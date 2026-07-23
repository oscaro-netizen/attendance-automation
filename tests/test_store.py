"""The Slack-user -> token mapping, which is the only state the service keeps."""
import os

from app.store import delete_employee, get_token, list_employees, put_token


def test_a_registered_token_can_be_read_back(db_path):
    put_token("U1", "tok-1", "ada", path=db_path)
    assert get_token("U1", path=db_path) == "tok-1"


def test_an_unknown_user_has_no_token(db_path):
    assert get_token("U_NOBODY", path=db_path) is None


def test_registering_again_replaces_the_token(db_path):
    """Re-registering is how an expired token gets refreshed."""
    put_token("U1", "old", "ada", path=db_path)
    put_token("U1", "new", path=db_path)
    assert get_token("U1", path=db_path) == "new"


def test_re_registering_without_a_label_keeps_the_old_one(db_path):
    put_token("U1", "old", "ada", path=db_path)
    put_token("U1", "new", path=db_path)
    assert list_employees(path=db_path)[0]["label"] == "ada"


def test_employees_can_be_removed(db_path):
    put_token("U1", "tok", path=db_path)
    assert delete_employee("U1", path=db_path) is True
    assert get_token("U1", path=db_path) is None


def test_removing_an_unknown_employee_reports_false(db_path):
    assert delete_employee("U_NOBODY", path=db_path) is False


def test_listing_does_not_expose_tokens(db_path):
    put_token("U1", "super-secret-token", "ada", path=db_path)
    row = list_employees(path=db_path)[0]
    assert "super-secret-token" not in str(dict(row))


def test_the_database_file_is_owner_only(db_path):
    """It holds bearer tokens, so it must not be world-readable."""
    put_token("U1", "tok", path=db_path)
    assert oct(os.stat(db_path).st_mode)[-3:] == "600"
