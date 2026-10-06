from scripts.check_mypy_baseline import diagnostics, new_diagnostics


def test_line_shifts_are_not_new_errors_but_different_errors_are():
    baseline = [{"path": "server/x.py", "message": 'Name "x" already defined on line <n>  [no-redef]', "count": 1}]
    moved = 'server/x.py:20: error: Name "x" already defined on line 10  [no-redef]'
    assert not new_diagnostics(moved, baseline)
    new = moved + '\nserver/x.py:21: error: Incompatible return value type  [return-value]'
    assert sum(new_diagnostics(new, baseline).values()) == 1


def test_baseline_counts_duplicates_and_does_not_ignore_other_files():
    baseline = [{"path": "server/x.py", "message": 'Bad argument  [arg-type]', "count": 1}]
    output = '\n'.join([
        'server/x.py:1: error: Bad argument  [arg-type]',
        'server/x.py:2: error: Bad argument  [arg-type]',
        'server/y.py:3: error: Bad argument  [arg-type]',
        'server/x.py:4: note: This is only a note',
    ])
    assert sum(diagnostics(output).values()) == 3
    assert sum(new_diagnostics(output, baseline).values()) == 2
