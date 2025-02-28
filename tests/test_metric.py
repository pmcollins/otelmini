from otelmini.metric import Counter, Meter


def test_meter():
    m = Meter("bob")
    c = m.create_counter("c")
    assert isinstance(c, Counter)


def test_counter_add_int():
    c = Counter("c")
    c.add(1)
    assert c._value == 1
