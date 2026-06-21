from spuk.live_insert import LiveInserter


def make_inserter():
    typed = []
    backed = []

    def type_fn(text):
        typed.append(text)

    def bs_fn(n):
        backed.append(n)

    return LiveInserter(type_fn=type_fn, backspace_fn=bs_fn), typed, backed


def test_first_update_types_without_backspace():
    ins, typed, backed = make_inserter()
    ins.update("hello")
    assert backed == []
    assert typed == ["hello"]


def test_second_update_erases_previous():
    ins, typed, backed = make_inserter()
    ins.update("hell")
    ins.update("hello world")
    assert backed == [4]          # erased "hell" (4 chars)
    assert typed == ["hell", "hello world"]


def test_update_empty_text_erases_provisional():
    ins, typed, backed = make_inserter()
    ins.update("abc")
    ins.update("")
    assert backed == [3]
    assert typed == ["abc", ""]


def test_commit_clears_provisional():
    ins, typed, backed = make_inserter()
    ins.update("hi")
    ins.commit()
    ins.update("new")   # no backspace — committed text is not provisional
    assert backed == []
    assert typed == ["hi", "new"]


def test_cancel_erases_provisional_text():
    ins, typed, backed = make_inserter()
    ins.update("draft")
    ins.cancel()
    assert backed == [5]
    assert typed == ["draft"]


def test_cancel_when_nothing_provisional_is_noop():
    ins, typed, backed = make_inserter()
    ins.cancel()
    assert backed == []
    assert typed == []


def test_unicode_len_counts_code_points():
    """len("über") = 4 code points → 4 backspaces."""
    ins, typed, backed = make_inserter()
    ins.update("über")
    ins.update("überall")
    assert backed == [4]
