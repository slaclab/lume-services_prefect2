from datetime import datetime
import pytest
import numpy as np
import pandas as pd
from PIL import Image
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from lume_services.results import (
    Result,
    ImpactResult,
    get_result_from_string,
    get_collections,
)
from lume_services.files import HDF5File, ImageFile
from lume_services.tests.files import SAMPLE_IMPACT_ARCHIVE, SAMPLE_IMAGE_FILE
from lume_services.services.results import MongodbResultsDBConfig, MongodbResultsDB


class TestBSON:

    numpy_array = np.array([1, 2, 3, 4, 5])
    pandas_dataframe = pd.DataFrame({"x": [0, 1, 2], "y": [1, 2, 3]})

    @pytest.fixture(scope="class")
    def bson_insert_numpy(self, results_db_service):

        result = Result(
            flow_id="test_flow_id",
            inputs={"input1": 2.0, "input2": self.numpy_array},
            outputs={
                "output1": 2.0,
                "output2": 3.0,
            },
        )

        rep = result.get_db_dict()
        results_db_service.insert_one(rep)

    @pytest.fixture(scope="class")
    def bson_insert_pandas(self, results_db_service):

        result = Result(
            flow_id="test_pandas_flow",
            inputs={"input1": 4.0, "input2": np.array([1, 2, 3, 4, 5])},
            outputs={
                "output1": 2.0,
                "output2": self.pandas_dataframe,
            },
        )

        rep = result.get_db_dict()
        results_db_service.insert_one(rep)

    @pytest.mark.usefixtures("bson_insert_numpy")
    def test_bson_get_numpy(self, results_db_service):

        query = {"inputs.input1": 2.0}
        selected = results_db_service.find(collection="generic", query=query)
        assert len(selected)

        assert isinstance(selected[0], np.ndarray)

    @pytest.mark.usefixtures("bson_insert_numpy")
    def test_numpy_query(self, results_db_service):

        query = {"inputs.input2": self.numpy_array}
        selected = results_db_service.find(collection="generic", query=query)

        assert len(selected)

        assert isinstance(selected[0], np.ndarray)

    @pytest.mark.usefixtures("bson_insert_pandas")
    def test_bson_get_pandas(self, results_db_service):

        query = {"flow_id": "test_pandas_flow"}
        selected = results_db_service.find(collection="generic", query=query)

        assert len(selected)

        assert isinstance(selected[0], pd.DataFrame)

    @pytest.mark.usefixtures("bson_insert_pandas")
    def test_pandas_query(self, results_db_service):

        query = {"ouputs.output2": self.pandas_dataframe}
        selected = results_db_service.find(collection="generic", query=query)

        assert len(selected)

        assert isinstance(selected[0], pd.DataFrame)


@pytest.mark.parametrize(
    ("string", "result_class_target"),
    [
        ("lume_services.results.generic:Result", Result),
        ("lume_services.results.impact:ImpactResult", ImpactResult),
        pytest.param(
            "incorrect.import.string",
            Result,
            marks=pytest.mark.xfail(strict=True),
        ),
    ],
)
def test_get_result_from_string(string, result_class_target):
    result_type = get_result_from_string(string)
    assert result_type == result_class_target


@pytest.fixture(scope="module", autouse=True)
def impact_result():
    return ImpactResult(
        flow_id="test_flow_id",
        inputs={
            "input1": 2.0,
            "input2": np.array([1, 2, 3, 4, 5]),
            "input3": "my_file.txt",
        },
        outputs={
            "output1": 2.0,
            "output2": np.array([1, 2, 3, 4, 5]),
            "output3": "my_file.txt",
        },
        plot_file=ImageFile(filename=SAMPLE_IMAGE_FILE, filesystem_identifier="local"),
        archive=HDF5File(filename=SAMPLE_IMPACT_ARCHIVE, filesystem_identifier="local"),
        pv_collection_isotime=datetime.now(),
        config={"config1": 1, "config2": 2},
    )


@pytest.fixture(scope="module", autouse=True)
def generic_result():
    return Result(
        flow_id="test_flow_id",
        inputs={"input1": 2.0, "input2": np.array([1, 2, 3, 4, 5])},
        outputs={
            "output1": 2.0,
            "output2": np.array([1, 2, 3, 4, 5]),
        },
    )


class TestResult:
    def test_create_generic_result_from_alias(self):
        Result(
            collection="generic",
            flow_id="test_flow_id",
            inputs={"input1": 4, "input2": 3},
            outputs={"output1": 1},
        )

    def test_to_json(self, generic_result):
        generic_result.json()

    def test_from_json(self, generic_result):
        json_rep = generic_result.json()
        Result.parse_raw(json_rep)

    def test_from_dict(self, generic_result):
        dictionary = generic_result.dict(by_alias=True)
        Result(**dictionary)


class TestImpactResult:
    def create_impact_result_from_alias(self):
        """Impact result fixture"""
        return ImpactResult(
            collection="impact",
            flow_id="test_flow_id",
            inputs={"input1": 4, "input2": 3},
            outputs={"output1": 1},
            archive={
                "filename": SAMPLE_IMPACT_ARCHIVE,
                "filesystem_identifier": "local",
            },
            plot_file={
                "filename": SAMPLE_IMAGE_FILE,
                "filesystem_identifier": "local",
            },
            pv_collection_isotime=datetime.utcnow(),
            config={"example_config": 1},
        )

    def test_to_json(self, impact_result):
        impact_result.json()

    def test_from_json(self, impact_result):
        json_rep = impact_result.json()
        ImpactResult.parse_raw(json_rep)

    def test_from_dict(self, impact_result):
        ImpactResult(**impact_result.get_db_dict())

    def test_load_image(self, impact_result, file_service):
        image = impact_result.plot_file.read(file_service=file_service)
        assert isinstance(image, (Image.Image,))


class TestMongodbResultsDBConfig:
    def test_construction(self):
        MongodbResultsDBConfig(
            database="results",
            host="localhost",
            username="user",
            port=3030,
            password="test",
        )

    def test_failed_construction(self):
        with pytest.raises(ValidationError):
            MongodbResultsDBConfig(
                database="results",
                host="localhost",
                username="user",
                port=3030,
            )


class TestMongodbResultsDB:
    def test_collections(self, results_db_service):
        # check collections represented in results service db
        collections = get_collections()
        assert all(
            [
                collection_name in results_db_service._results_db._collections.get()
                for collection_name in collections.keys()
            ]
        )

    def test_mongo_results_db_init(self, lume_services_settings):
        MongodbResultsDB(lume_services_settings.results_db)


class TestResultsDBService:
    @pytest.fixture(scope="class")
    def generic_result_insert(self, generic_result, results_db_service):
        test_generic_result_insert = results_db_service.insert_one(
            generic_result.get_db_dict()
        )
        assert test_generic_result_insert is not None

        # confirm duplicate raises error
        with pytest.raises(DuplicateKeyError):
            test_generic_result_insert = results_db_service.insert_one(
                generic_result.get_db_dict()
            )

    def test_generic_result_query(
        self, results_db_service, generic_result, generic_result_insert
    ):
        res = results_db_service.find(
            collection=generic_result.model_type,
            query={
                "flow_id": generic_result.flow_id,
                "inputs": generic_result.inputs,
                "outputs": generic_result.outputs,
            },
        )

        new_generic_obj = Result(**res[0])

        assert generic_result.flow_id == new_generic_obj.flow_id
        assert generic_result.inputs == new_generic_obj.inputs
        assert generic_result.outputs == new_generic_obj.outputs

    @pytest.fixture(scope="class")
    def impact_result_insert(self, impact_result, results_db_service):

        test_impact_result_insert = results_db_service.insert_one(
            impact_result.get_db_dict()
        )
        assert test_impact_result_insert is not None

        # confirm duplicate raises error
        with pytest.raises(DuplicateKeyError):
            test_impact_result_insert = results_db_service.insert_one(
                impact_result.get_db_dict()
            )

    def test_impact_result_query(
        self, results_db_service, impact_result, impact_result_insert
    ):
        res = results_db_service.find(
            collection=impact_result.model_type,
            query={
                "flow_id": impact_result.flow_id,
                "inputs": impact_result.inputs,
                "outputs": impact_result.outputs,
            },
        )

        new_impact_obj = ImpactResult(**res[0])

        assert impact_result.flow_id == new_impact_obj.flow_id
        assert impact_result.inputs == new_impact_obj.inputs
        assert impact_result.outputs == new_impact_obj.outputs
        assert impact_result.archive == new_impact_obj.archive
        assert impact_result.plot_file == new_impact_obj.plot_file
        assert (
            impact_result.pv_collection_isotime == new_impact_obj.pv_collection_isotime
        )
        assert impact_result.config == new_impact_obj.config

    def test_find_all(self, generic_result, results_db_service):
        res = results_db_service.find_all(collection=generic_result.model_type)
        assert isinstance(res, list)


class TestResultsInsertMethods:
    def test_generic_result_insert_by_method(self, generic_result, results_db_service):
        generic_result.insert(results_db_service=results_db_service)

        # confirm duplicate raises error
        with pytest.raises(DuplicateKeyError):
            generic_result.insert(results_db_service=results_db_service)

    def test_load_generic_result(self, generic_result, results_db_service):
        new_generic_result = Result.load_from_query(
            {
                "flow_id": generic_result.flow_id,
                "inputs": generic_result.inputs,
                "outputs": generic_result.outputs,
            },
            results_db_service=results_db_service,
        )

        assert generic_result.flow_id == new_generic_result.flow_id
        assert generic_result.inputs == new_generic_result.inputs
        assert generic_result.outputs == new_generic_result.outputs

    def test_impact_result_insert_by_method(self, impact_result, results_db_service):
        impact_result.insert(results_db_service=results_db_service)

        # confirm duplicate raises error
        with pytest.raises(DuplicateKeyError):
            impact_result.insert(results_db_service=results_db_service)

    def test_load_impact_result(self, impact_result, results_db_service):
        new_impact_obj = ImpactResult.load_from_query(
            {
                "flow_id": impact_result.flow_id,
                "inputs": impact_result.inputs,
                "outputs": impact_result.outputs,
            },
            results_db_service=results_db_service,
        )

        assert impact_result.flow_id == new_impact_obj.flow_id
        assert impact_result.inputs == new_impact_obj.inputs
        assert impact_result.outputs == new_impact_obj.outputs
        assert impact_result.archive == new_impact_obj.archive
        assert impact_result.plot_file == new_impact_obj.plot_file
        assert (
            impact_result.pv_collection_isotime == new_impact_obj.pv_collection_isotime
        )
        assert impact_result.config == new_impact_obj.config
