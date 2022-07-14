from prefect import Flow
from pydantic import BaseModel, validator
from prefect.run_configs import LocalRun
from typing import Optional, Dict, Any
import logging
import warnings
import os

from lume_services.services.scheduling.backends import Backend
from lume_services.errors import EmptyResultError, LocalBackendError, TaskNotInFlowError

logger = logging.getLogger(__name__)


class LocalRunConfig(BaseModel):
    """Local run configuration. If no directory is found at the filepath passed as
    working_dir, an error will be raised.

    Attributes:
        env (Optional[Dict[str, str]]): Dictionary of environment variables to use for
            run
        working_dir (Optional[str]): Working directory

    """

    env: Optional[Dict[str, str]]
    working_dir: Optional[str] = str(os.getcwd())

    @validator("working_dir", pre=True)
    def validate(cls, v):
        """Pydantic validator checking working directory existence"""
        if not os.path.isdir(v):
            raise FileNotFoundError("No directory found at %s", v)

        return v


class LocalBackend(Backend):
    """Backend used for local execution. This backend will raise errors on any function
    calls requiring registration with the Prefect server.

    Attributes:
        run_config (Optional[LocalRunConfig]): Default configuration object for a given
            run.

    """

    def run(
        self,
        data: Dict[str, Any],
        run_config: Optional[LocalRunConfig],
        flow: Flow,
        **kwargs
    ) -> None:
        """Run flow execution. Does not return result.

        Args:
            data (Optional[Dict[str, Any]]): Dictionary mapping flow parameter name to
                value
            run_config (Optional[LocalRunConfig]): LocalRunConfig object to configure
                flow fun.
            flow (Flow): Prefect flow to execute
            **kwargs: Keyword arguments to intantiate the LocalRunConfig.

        """

        if run_config is not None and len(kwargs):
            warnings.warn(
                "Both run_config and kwargs passed to LocalBackend.run. Flow\
                will execute using passed run_config."
            )

        if run_config is None:
            run_config = LocalRunConfig(**kwargs)

        # convert to Prefect LocalRun
        run_config = LocalRun(**run_config.dict(exclude_none=True))

        # apply run config
        flow.run_config = run_config
        flow.run(parameters=data)

    def run_and_return(
        self,
        data: Dict[str, Any],
        run_config: Optional[LocalRunConfig],
        task_slug: Optional[str],
        flow: Flow,
        **kwargs
    ) -> Any:
        """Run flow execution and return result.

        Args:
            flow (Flow): Prefect flow to execute.
            data (Optional[Dict[str, Any]]): Dictionary mapping flow parameter name to
                value.
            run_config (Optional[LocalRunConfig]): LocalRunConfig object to configure
                flow fun.
            task_slug (Optional[str]): Slug of task to return result. If no task slug
                is passed, will return the flow result.

        """

        if run_config is None:
            run_config = LocalRunConfig(**kwargs)

        # convert to Prefect LocalRun
        run_config = LocalRun(**run_config.dict(exclude_none=True))

        # apply run config
        flow.run_config = run_config
        flow_run = flow.run(parameters=data)

        result = flow_run.result

        if result is None:
            raise EmptyResultError

        slug_to_task_map = {slug: task for task, slug in flow.slugs.items()}

        # account for task slug
        if task_slug is not None:
            task = slug_to_task_map.get(task_slug)

            if task is None:
                raise TaskNotInFlowError

            return result[task].result

        # else return dict of task slug to value
        else:
            return {
                slug: result[task].result for slug, task in slug_to_task_map.items()
            }

    def create_project(self, *args, **kwargs) -> None:
        """Raise LocalBackendError for calls to register_flow server-type method.

        Raises:
            LocalBackendError

        """
        raise LocalBackendError

    def register_flow(self, *args, **kwargs) -> None:
        """Raise LocalBackendError for calls to register_flow server-type method.

        Raises:
            LocalBackendError

        """
        raise LocalBackendError

    def load_flow(self, *args, **kwargs) -> None:
        """Raise LocalBackendError for calls to load_flow server-type method.

        Raises:
            LocalBackendError

        """
        raise LocalBackendError
