import bambi as bmb
import pytest

from hssm.utils import Param, _parse_bambi


def test_param_non_regression():

    param_value = Param("a", prior=0.5)

    param_dict = Param(
        "z",
        prior={
            "name": "Uniform",
            "upper": 0.5,
            "lower": 0.8,
        },
    )

    param_prior = Param("t", prior=bmb.Prior("Uniform", upper=0.5, lower=0.8))

    assert param_value.name == "a"
    assert isinstance(param_dict.prior, bmb.Prior)
    assert param_dict.prior == param_prior.prior
    assert not param_value.is_regression()

    assert param_value.link is None
    assert param_prior.formula is None

    formula1, d1, link1 = param_dict._parse_bambi()  # pylint: disable=W0212
    formula2, d2, link2 = param_prior._parse_bambi()  # pylint: disable=W0212

    assert formula1 is None and formula2 is None
    assert isinstance(d1["z"], bmb.Prior)
    assert d1["z"] == d2["t"]
    assert link1 is None and link2 is None

    assert repr(param_value) == "a = 0.5"
    assert repr(param_dict) == f"z ~ {param_dict.prior}"

    with pytest.raises(
        ValueError, match="`link` should be None if no regression is specified."
    ):
        Param("t", 0.5, link="identity")

    with pytest.raises(ValueError, match="Please specify a value or prior for a."):
        Param("a")


def test_param_regression():

    fake_func = lambda x: x * 2  # pylint: disable=C3001
    fake_link = bmb.Link(
        "Fake", link=fake_func, linkinv=fake_func, linkinv_backend=fake_func
    )

    priors_dict = {
        "Intercept": {
            "name": "Normal",
            "mu": 0,
            "sigma": 0.5,
        },
        "x1": bmb.Prior("Normal", mu=0, sigma=0.5),
    }

    param_reg_formula1 = Param("a", formula="1 + x1", prior=priors_dict)
    param_reg_formula2 = Param(
        "a", formula="a ~ 1 + x1", prior=priors_dict, link=fake_link
    )

    param_reg_parent = Param("a", formula="a ~ 1 + x1", is_parent=True)

    assert param_reg_formula1.formula == "a ~ 1 + x1"
    assert isinstance(param_reg_formula2.link, bmb.Link)

    dep_priors2 = param_reg_formula2.prior

    assert isinstance(dep_priors2["Intercept"], bmb.Prior)
    assert dep_priors2["Intercept"] == dep_priors2["x1"]

    formula1, d1, link1 = param_reg_formula1._parse_bambi()  # pylint: disable=W0212
    formula2, d2, link2 = param_reg_formula2._parse_bambi()  # pylint: disable=W0212

    assert formula1 == formula2
    assert d1 == d2
    assert link1["a"] == "identity"
    assert link2["a"].name == "Fake"

    formula3, d3, _ = param_reg_parent._parse_bambi()  # pylint: disable=W0212

    assert formula3 == "c(rt, response) ~ 1 + x1"
    assert param_reg_parent.formula == "a ~ 1 + x1"

    assert d3 is None

    rep = repr(param_reg_parent)
    lines = rep.split("\r\n")
    assert lines[2] == "Unspecified, using defaults"


def test__parse_bambi():
    prior_dict = {"name": "Uniform", "lower": 0.3, "upper": 1.0}
    prior_obj = bmb.Prior("Uniform", lower=0.3, upper=1.0)

    param_non_parent_non_regression = Param("a", prior=prior_dict)
    param_parent_non_regression = Param("v", prior=prior_dict, is_parent=True)

    param_non_parent_regression = Param(
        "a",
        formula="1 + x1",
        prior={
            "Intercept": prior_dict,
            "x1": prior_dict,
        },
    )

    param_parent_regression = Param(
        "v",
        formula="1 + x1",
        prior={
            "Intercept": prior_dict,
            "x1": prior_dict,
        },
        is_parent=True,
    )

    empty_list = []
    list_one_non_parent_non_regression = [param_non_parent_non_regression]
    list_one_non_parent_regression = [param_non_parent_regression]
    list_one_parent_non_regression = [param_parent_non_regression]
    list_one_parent_regression = [param_parent_regression]

    f0, p0, l0 = _parse_bambi(empty_list)

    assert f0.main == "c(rt, response) ~ 1"
    assert p0 is None
    assert l0 == "identity"

    f1, p1, l1 = _parse_bambi(list_one_non_parent_non_regression)

    assert f1.main == "c(rt, response) ~ 1"
    assert p1["a"] == prior_obj
    assert l1 == "identity"

    f2, p2, l2 = _parse_bambi(list_one_non_parent_regression)

    assert f2.main == "c(rt, response) ~ 1"
    assert f2.additionals[0] == "a ~ 1 + x1"
    assert p2["a"]["Intercept"] == prior_obj
    assert p2["a"]["x1"] == prior_obj
    assert l2 == {"a": "identity"}

    f3, p3, l3 = _parse_bambi(list_one_parent_non_regression)

    assert f3.main == "c(rt, response) ~ 1"
    assert p3["c(rt, response)"]["Intercept"] == prior_obj
    assert l3 == {"v": "identity"}

    f4, p4, l4 = _parse_bambi(list_one_parent_regression)

    assert f4.main == "c(rt, response) ~ 1 + x1"
    assert p4["c(rt, response)"]["Intercept"] == prior_obj
    assert p4["c(rt, response)"]["x1"] == prior_obj
    assert l4 == {"v": "identity"}