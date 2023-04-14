from pathlib import Path

import numpy as np
import onnx
import onnxruntime
import pytensor
import pytensor.tensor as pt
import pytest

from hssm.wfpt import lan
from hssm.wfpt.lan.onnx2pt import pt_interpret_onnx
from hssm.wfpt.lan.onnx2xla import interpret_onnx

pytensor.config.floatX = "float32"


@pytest.fixture(scope="module")
def fixture_path():
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def onnx_session():

    fixture_dir = Path(__file__).parent / "fixtures"
    model_path = str(fixture_dir / "test.onnx")

    return onnxruntime.InferenceSession(model_path, None)


def test_interpret_onnx(onnx_session, fixture_path):

    data = np.random.rand(1, 7).astype(np.float32)

    input_name = onnx_session.get_inputs()[0].name
    output_name = onnx_session.get_outputs()[0].name

    result_onnx = onnx_session.run([output_name], {input_name: data})[0]

    model = onnx.load(fixture_path / "test.onnx")
    result_jax = np.asarray(interpret_onnx(model.graph, data)[0])
    result_pytensor = pt_interpret_onnx(model.graph, data)[0].eval()

    np.testing.assert_almost_equal(result_jax, result_onnx, decimal=4)
    # For some reason pytensor and onnx (jax) version results are slightly different
    np.testing.assert_almost_equal(result_pytensor, result_onnx, decimal=4)


def test_make_jax_logp_funcs_from_onnx(fixture_path):
    model = onnx.load(fixture_path / "test.onnx")

    jax_logp, _, jax_logp_nojit = lan.make_jax_logp_funcs_from_onnx(
        model, params_is_reg=[False] * 5
    )

    data = np.random.rand(10, 2)
    params_all_scalars = np.random.rand(5)

    result_boxed_function = jax_logp(data, *params_all_scalars)

    # ensures it returns a vector
    assert len(result_boxed_function) == 10

    input_matrix = np.hstack([np.broadcast_to(params_all_scalars, (10, 5)), data])
    np.testing.assert_array_almost_equal(
        result_boxed_function,
        interpret_onnx(model.graph, input_matrix)[0].squeeze(),
    )

    np.testing.assert_array_almost_equal(
        result_boxed_function,
        interpret_onnx(model.graph, input_matrix)[0].squeeze(),
    )

    v = np.random.rand(10)
    input_matrix[:, 0] = v

    jax_logp, _, jax_logp_nojit = lan.make_jax_logp_funcs_from_onnx(
        model, params_is_reg=[True] + [False] * 4
    )

    np.testing.assert_array_almost_equal(
        jax_logp(data, v, *params_all_scalars[1:]),
        interpret_onnx(model.graph, input_matrix)[0].squeeze(),
    )

    np.testing.assert_array_almost_equal(
        jax_logp_nojit(data, v, *params_all_scalars[1:]),
        interpret_onnx(model.graph, input_matrix)[0].squeeze(),
    )


def test_make_jax_logp_ops(fixture_path):
    model = onnx.load(fixture_path / "test.onnx")

    jax_logp_op = lan.make_jax_logp_ops(
        *lan.make_jax_logp_funcs_from_onnx(model, params_is_reg=[False] * 5)
    )
    pytensor_logp = lan.make_pytensor_logp(model, params_is_reg=[False] * 5)

    data = np.random.rand(10, 2)
    params_all_scalars = np.random.rand(5).astype(np.float32)

    jax_loglik = jax_logp_op(data, *params_all_scalars)
    pt_loglik = pytensor_logp(data, *params_all_scalars)

    np.testing.assert_array_almost_equal(
        np.asarray(jax_loglik.eval()), pt_loglik.eval(), decimal=3
    )

    jax_logp_op = lan.make_jax_logp_ops(
        *lan.make_jax_logp_funcs_from_onnx(model, params_is_reg=[True] + [False] * 4)
    )
    pytensor_logp = lan.make_pytensor_logp(model, params_is_reg=[True] + [False] * 4)

    v = np.random.rand(10)

    jax_loglik = jax_logp_op(data, v, *params_all_scalars[1:])
    pt_loglik = pytensor_logp(data, v, *params_all_scalars[1:])

    np.testing.assert_array_almost_equal(jax_loglik.eval(), pt_loglik.eval(), decimal=4)

    v = pt.as_tensor_variable(np.random.rand())

    params_with_v = [v, *params_all_scalars[1:]]
    data = data.astype(np.float32)

    jax_logp_op = lan.make_jax_logp_ops(
        *lan.make_jax_logp_funcs_from_onnx(model, params_is_reg=[False] * 5)
    )
    pytensor_logp = lan.make_pytensor_logp(model, params_is_reg=[False] * 5)

    jax_loglik = jax_logp_op(data, *params_with_v)
    pt_loglik = pytensor_logp(data, *params_with_v)

    np.testing.assert_array_almost_equal(
        pytensor.grad(jax_loglik.sum(), wrt=v).eval(),
        pytensor.grad(pt_loglik.sum(), wrt=v).eval(),
        decimal=4,
    )
