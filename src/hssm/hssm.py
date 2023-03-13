from __future__ import annotations

from typing import Callable, List

import bambi as bmb
import pandas as pd
import pytensor
from numpy.typing import ArrayLike

from hssm import wfpt
from hssm.utils import Param, _parse_bambi
from hssm.wfpt.config import default_model_config

LogLikeFunc = Callable[..., ArrayLike]

# add custom link function
class HSSM:
    """
    The Hierarchical Sequential Sampling Model (HSSM) class.

    Args:
    data (pandas.DataFrame): A pandas DataFrame with the minimum requirements of
        containing the data with the columns 'rt' and 'response'.
    model_name (str): The name of the model to use. Default is "ddm".
    Current default implementations are "ddm" | "lan" | "custom".
        ddm - Computes the log-likelihood of the drift diffusion model f(t|v,a,z) using
        the method and implementation of Navarro & Fuss, 2009.
        angle - Likelihood Approximation Network (LAN) extension for the Wiener
         First-Passage Time (WFPT) distribution.
    include (List[dict], optional): A list of dictionaries specifying additional
     parameters to include in the model. Defaults to None. Priors specification range:
        v: Mean drift rate. (-inf, inf).
        sv: Standard deviation of the drift rate [0, inf).
        a: Value of decision upper bound. (0, inf).
        z: Normalized decision starting point. (0, 1).
        t: Non-decision time [0, inf).
        theta: [0, inf).
    model_config (dict, optional): A dictionary containing the model
     configuration information. Defaults to None.

    Attributes:
        list_params (list): The list of parameter names.
        model_name (str): The name of the model.
        model_distribution: A SSM model object.
        likelihood: A Bambi likelihood object.
        family: A Bambi family object.
        priors (dict): A dictionary containing the prior distribution
         of parameters.
        formula (str): A string representing the model formula.
        params (list): A list of Param objects representing model parameters.
        model: A Bambi model object.

    Methods:
        _transform_params: A method to transform priors, link and formula
         into Bambi's format.
        sample: A method to sample posterior distributions.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        model: str | None = "ddm",
        include: List[dict] | None = None,
        model_config: dict | None = None,
        loglik: LogLikeFunc | pytensor.graph.Op | None = None,
    ):
        if model not in ["angle", "custom", "ddm"]:
            raise ValueError("Please provide a correct model_name")

        self.model_config = (
            model_config if model_config else default_model_config[model]
        )

        self.list_params = self.model_config["list_params"]
        if model == "ddm":
            self.model_distribution = wfpt.WFPT
        elif model == "angle":
            self.model_distribution = wfpt.make_lan_distribution(
                model=self.model_config["loglik_path"],
                list_params=self.list_params,
                backend=self.model_config["backend"],
            )
        elif model == "custom":
            self.model_distribution = wfpt.make_distribution(
                loglik=loglik, list_params=self.list_params
            )

        self.likelihood = bmb.Likelihood(
            self.model_config["loglik_kind"],
            params=self.list_params,
            parent=self.model_config["list_params"][0],
            dist=self.model_distribution,
        )

        self.formula = self.model_config["formula"]
        self.priors = self.model_config["prior"]

        self._transform_params(include)  # type: ignore

        self.family = bmb.Family(
            self.model_config["loglik_kind"],
            likelihood=self.likelihood,
            link=self.link,
        )

        self.model = bmb.Model(
            self.formula, data, family=self.family, priors=self.priors
        )

    def _transform_params(self, include: List[dict]) -> None:
        """
        This function transforms a list of dictionaries containing
         parameter information into a list of Param objects.
          It also creates a formula, priors, and a link for the Bambi
           package based on the parameters.

        Parameters:

        include (List[dict]): A list of dictionaries containing information
         about the parameters.
        """
        processed = []
        self.params = []
        if include:
            for dictionary in include:
                processed.append(dictionary["name"])
                if dictionary["name"] == self.list_params[0]:
                    self.params.append(Param(is_parent=True, **dictionary))
                else:
                    self.params.append(Param(**dictionary))

        for param in self.list_params:
            if param not in processed:
                if param == self.list_params[0]:
                    self.params.append(
                        Param(
                            name=param,
                            prior=self.priors[param]["Intercept"],
                            is_parent=True,
                        )
                    )
                else:
                    self.params.append(Param(name=param, prior=self.priors[param]))

        if len(self.params) != len(self.list_params):
            raise ValueError("Please provide a correct set of priors")

        self.formula, self.priors, self.link = _parse_bambi(self.params)

    def sample(
        self,
        cores: int = 2,
        draws: int = 500,
        tune: int = 500,
        mp_ctx: str = "fork",
        sampler: str = "pytensor",
    ):
        """
        Perform posterior sampling using the `fit` function of Bambi.

        Args:
            cores (int): The number of cores to use for parallel sampling.
             Default is 2.
            draws (int): The number of posterior samples to draw. Default is 500.
            tune (int): The number of tuning steps to perform before starting
             to draw posterior samples. Default is 500.
            mp_ctx (str): The multiprocessing context to use. Default is "fork".
            sampler (str): The sampler to use. Can be either "jax" or "pytensor".
             Default is "pytensor".

        Returns:
            The posterior samples, which is an instance of the
             `arviz.InferenceData` class.
        """
        if sampler == "jax":
            return self.model.fit(
                cores=cores,
                draws=draws,
                tune=tune,
                inference_method="nuts_numpyro",
                chain_method="parallel",
            )
        else:
            return self.model.fit(cores=cores, draws=draws, tune=tune, mp_ctx=mp_ctx)