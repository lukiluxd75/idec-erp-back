"""IDEC ERP backend package.

Every other directory under `app/` already carries an `__init__.py`; this one
was the only gap, and `app` worked anyway as an implicit namespace package.
Test discovery does not accept that: `unittest discover -s app` rejects a
namespace package as a start directory ("Start directory is not importable"),
which is why the 11 test modules in `app/domains/*/tests/` could only ever be
run one by one. With this file in place the whole suite runs in one command:

    python -m unittest discover -s app -p "test_*.py" -t .
"""
