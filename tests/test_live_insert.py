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


def test_update_empty_text_commits_keeps_text():
    """An empty partial is Apple signalling an utterance boundary, not a request
    to erase. Already-typed text is kept (committed), not backspaced away."""
    ins, typed, backed = make_inserter()
    ins.update("abc")
    ins.update("")
    assert backed == []        # nothing erased
    assert typed == ["abc"]    # text kept as-is


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
    """A tail correction backspaces one per code point ("ß" is multi-byte in
    UTF-8 but a single code point → one backspace, not two)."""
    ins, typed, backed = make_inserter()
    ins.update("groß")     # 4 code points
    ins.update("gros")     # shares "gro" (3); erase "ß" (1 code point); type "s"
    assert backed == [1]
    assert typed == ["groß", "s"]


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


def test_reset_partial_after_pause_keeps_prior_text():
    """The bug: Apple's recognizer resets its transcript after a ~1s pause and
    emits a fresh partial for the next utterance (a known SFSpeechRecognizer
    behavior). The prior text must be kept (committed) and the new utterance
    appended — NOT backspaced away."""
    ins, typed, backed = make_inserter()
    ins.update("hello world")            # first utterance streams in
    ins.update("how are you")            # pause → brand-new utterance, no shared prefix
    assert backed == []                  # prior text must NOT be erased
    assert "".join(typed) == "hello world how are you"   # appended, space-separated


def test_reset_partial_sharing_one_letter_is_not_a_correction():
    """A new utterance can coincidentally share a first letter with the prior
    text ('hello world' → 'how'). That single-char overlap must still count as a
    reset (keep + append), not a near-total backspace-correction."""
    ins, typed, backed = make_inserter()
    ins.update("hello world")
    ins.update("how")                    # shares only 'h'
    assert backed == []
    assert "".join(typed) == "hello world how"
