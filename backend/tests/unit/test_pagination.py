from mtgvault.api.pagination import PageParams, ResultPage


def test_offset_follows_the_page() -> None:
    assert PageParams().offset == 0
    assert PageParams(page=3, page_size=20).offset == 40


def test_has_next_is_true_only_while_more_items_remain() -> None:
    assert ResultPage[int](items=[1], page=1, page_size=1, total=2).has_next
    assert not ResultPage[int](items=[2], page=2, page_size=1, total=2).has_next
    assert not ResultPage[int](items=[], page=1, page_size=50, total=0).has_next
