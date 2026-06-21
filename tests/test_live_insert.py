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


def test_growing_update_keeps_common_prefix():
    ins, typed, backed = make_inserter()
    ins.update("hell")
    ins.update("hello world")
    assert backed == []                  # "hell" is a prefix — nothing erased
    assert typed == ["hell", "o world"]  # only the new suffix is typed


def test_update_empty_text_erases_provisional():
    ins, typed, backed = make_inserter()
    ins.update("abc")
    ins.update("")
    assert backed == [3]
    assert typed == ["abc"]   # empty suffix → no extra type call


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


def test_backspace_counts_code_points_not_bytes():
    """A fully-diverging update backspaces one per code point ("über" = 4)."""
    ins, typed, backed = make_inserter()
    ins.update("über")     # 4 code points (ü is multi-byte in UTF-8 but 1 code point)
    ins.update("x")        # shares no prefix → erase all 4, type "x"
    assert backed == [4]
    assert typed == ["über", "x"]


def test_revised_partial_backspaces_only_divergent_tail():
    ins, typed, backed = make_inserter()
    ins.update("their")
    ins.update("there")          # common "the" (3); erase "ir" (2); type "re"
    assert backed == [2]
    assert typed == ["their", "re"]


def test_identical_partial_is_noop():
    ins, typed, backed = make_inserter()
    ins.update("hello")
    ins.update("hello")          # nothing changed → no keystrokes
    assert backed == []
    assert typed == ["hello"]
