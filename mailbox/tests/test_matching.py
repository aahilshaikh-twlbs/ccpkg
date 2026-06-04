from mailbox.matching import path_matches


def test_exact_match():
    assert path_matches("/a/b/c.py", "/a/b/c.py") is True


def test_exact_non_match():
    assert path_matches("/a/b/c.py", "/a/b/d.py") is False


def test_star_within_dir():
    assert path_matches("/a/b/*.py", "/a/b/c.py") is True
    assert path_matches("/a/b/*.py", "/a/b/utils.py") is True


def test_star_does_not_cross_dir():
    assert path_matches("/a/b/*.py", "/a/b/sub/c.py") is False


def test_star_partial_segment():
    assert path_matches("/a/b/test_*.py", "/a/b/test_thing.py") is True
    assert path_matches("/a/b/test_*.py", "/a/b/thing.py") is False


def test_doublestar_recursive():
    assert path_matches("/a/b/**", "/a/b/c.py") is True
    assert path_matches("/a/b/**", "/a/b/sub/deep/c.py") is True


def test_doublestar_recursive_with_suffix():
    assert path_matches("/a/**/c.py", "/a/b/c.py") is True
    assert path_matches("/a/**/c.py", "/a/b/d/e/c.py") is True
    assert path_matches("/a/**/c.py", "/a/b/c.js") is False


def test_question_single_char():
    assert path_matches("/a/b/c?.py", "/a/b/c1.py") is True
    assert path_matches("/a/b/c?.py", "/a/b/c12.py") is False


def test_question_does_not_match_slash():
    assert path_matches("/a/b?c.py", "/a/b/c.py") is False


def test_dir_prefix_coverage():
    assert path_matches("/a/b", "/a/b/c.py") is True
    assert path_matches("/a/b", "/a/b/sub/c.py") is True


def test_dir_prefix_exact_dir():
    assert path_matches("/a/b", "/a/b") is True


def test_dir_prefix_not_sibling():
    # "/a/b" must not match "/a/bc.py" — prefix is a directory boundary
    assert path_matches("/a/b", "/a/bc.py") is False


def test_non_match_across_dirs():
    assert path_matches("/a/b/c.py", "/x/y/z.py") is False


def test_regex_special_chars_are_literal():
    # dots and plus in the glob must be treated literally, not as regex metachars
    assert path_matches("/a/b/c.py", "/a/bxpy") is False
    assert path_matches("/a/b+c.py", "/a/b+c.py") is True
    assert path_matches("/a/b+c.py", "/a/bc.py") is False
