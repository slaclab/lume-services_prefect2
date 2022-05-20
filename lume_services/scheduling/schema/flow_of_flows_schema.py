from pydantic import BaseModel, validator
from prefect.backend.flow import FlowView
from typing import List, Optional, Dict
from prefect.tasks.prefect import create_flow_run, wait_for_flow_run, get_task_run_result
from prefect import Flow as PrefectFlow
from prefect import Parameter, Task

# Pydantic schema describing flow of flows composition


class ParameterNotInFlowError(Exception):
    def __init__(self, parameter_name: str, flow_name: str):
        self.flow_name = flow_name
        self.parameter_name = parameter_name
        self.message = f"Parameter {self.parameter_name} not in flow {self.flow_name}."
        super().__init__(self.message)


class ParentFlowNotInFlowsError(Exception):
    def __init__(self, flow_name: str, flows: List[str]):
        self.flow_name = flow_name
        self.flows = flows
        self.message = (
            f"Parent flow {self.flow_name} not in flows: {', '.join(self.flows)}."
        )
        super().__init__(self.message)


class TaskNotInFlowError(Exception):
    def __init__(self, flow_name: str, task_name: str):
        self.flow_name = flow_name
        self.task_name = task_name
        self.message = f"Task {flow_name} not in flow {task_name}."
        super().__init__(self.message)


class MappedParameter(BaseModel):
    name: str
    parent_flow_name: str
    parent_task_name: str


class Flow(BaseModel):
    name: str
    project_name: str
    parameters: Dict[str, Parameter]
    mapped_parameters: Optional[Dict[str, MappedParameter]]
    prefect_flow: PrefectFlow
    task_slugs: Dict[str, str]

    class Config:
        arbitrary_types_allowed = True


class FlowOfFlows(BaseModel):
    name: str
    project_name: str
    composing_flows: dict

    _flows: dict = {}

    @validator("composing_flows", pre=True)
    def validate(cls, v: List[dict]):
        flows = {}

        # validate composing flow existence
        for flow in v:
            deserialized_flow = FlowView.from_flow_name(
                flow["name"], project_name=flow["project_name"], last_updated=True
            ).flow

            # organize data 
            parameters = {parameter.name: parameter for parameter in deserialized_flow.parameters()}

            mapped_parameters = None
            if flow.get("mapped_parameters") is not None:
                mapped_parameters = {param["name"]: param for param in flow.get("mapped_parameters")}

            task_slugs = {task.name: task.slug for task in deserialized_flow.get_tasks()}

            # compose flow objects
            flows[flow["name"]] = Flow(
                name = flow["name"],
                prefect_flow = deserialized_flow,
                parameters = parameters,
                task_slugs = task_slugs,
                project_name = flow["project_name"],
                mapped_parameters=mapped_parameters
            )

        # validate flow parameters
        for flow_name, flow in flows.items():
            if flow.mapped_parameters is not None:
                for parameter_name, parameter in flow.mapped_parameters.items():

                    # validate parameter is in flow spec
                    parameter_obj = flow.parameters.get(parameter_name)
                    if parameter_obj is None:
                        raise ParameterNotInFlowError(parameter_name, flow_name)

                    # validate parent flow is included in listed flows
                    parent_flow = flows.get(parameter.parent_flow_name)
                    if parent_flow is None:
                        raise ParentFlowNotInFlowsError(
                            parameter.parent_flow_name, list(flows.keys())
                        )

                    # validate task is in the parent flow
                    task = parent_flow.task_slugs.get(parameter.parent_task_name)
                    if task is None:
                        raise TaskNotInFlowError(
                            parameter.parent_flow_name, parameter.parent_task_name
                        )

                    # TODO: Add validation of parameter type against result type

        return flows

    def compose(self):

        # compose flow of flows
        with PrefectFlow(self.name) as flow_of_flows:

            flow_runs = {}
            flow_waits = {}
            params = {}

            for i, (flow_name, flow) in enumerate(self.composing_flows.items()):

                # begin by creating parameters for all flow parameters
                flow_params = {}
                for param_name, param in flow.parameters.items():
                    # do not register mapped parameters as flow parameters
                    if flow.mapped_parameters is not None and param_name in flow.mapped_parameters:
                        continue

                    param.name = f"{flow_name}-{param_name}"
                    params[param.name] = param

                    # use original param name for flow config
                    flow_params[param_name] = param

                # set up entry task
                if i == 0:
                    flow_run = create_flow_run(flow_name=flow_name, project_name=flow.project_name, parameters=flow_params)

                #task_run_result = flow_run.get_task_run_result(slug=...)
                elif i > 0:

                    # create references to parameters
                    upstream_flows = set()
                    if flow.mapped_parameters is not None:

                        # update flow_params with mapping
                        for param_name, mapped_param in flow.mapped_parameters.items():
                            task_slug = self.composing_flows[mapped_param.parent_flow_name].task_slugs[mapped_param.parent_task_name]

                            # use task run result as input param
                            task_run_result = get_task_run_result(flow_runs[mapped_param.parent_flow_name], task_slug)

                            # track param name with result
                            flow_params[param_name] = task_run_result

                            # add flow to upstream
                            upstream_flows.add(mapped_param.parent_flow_name)

                        print("Creating flow")
                        print(flow_params)
                        print(flow_name)
                        flow_run = create_flow_run(flow_name=flow_name, project_name=flow.project_name, parameters=flow_params)
                        print("Created")

                    # configure upstreams
                    for upstream in upstream_flows:
                        flow_run.set_upstream(flow_waits[upstream])
            
                flow_wait = wait_for_flow_run(flow_run, raise_final_state=True)
                flow_runs[flow_name] = flow_run
                flow_waits[flow_name] = flow_wait

            print("Composed flow")

                # 


        # validate flow of flows
        flow_of_flows.validate()
        flow_id = flow_of_flows.register(project_name=self.project_name)
        return flow_of_flows

    def compose_local(self):
        """
        
        Note:
            Prefect 1.0 does not allow subflow run without previous registration with 
            the server. This function is a workaround, but will be massively simplified
            once moved to Prefect 2.0, which does support direct subflow run.
        """
        ...


