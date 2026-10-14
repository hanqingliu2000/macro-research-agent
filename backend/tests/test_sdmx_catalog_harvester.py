from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.knowledge.harvest.sdmx import (
    SdmxCatalogHarvester,
    SdmxProviderConfig,
)
from macro_research_agent.knowledge.source_index import SourceIndexRepository

SDMX_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<mes:Structure xmlns:mes="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
 xmlns:str="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
 xmlns:com="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
 <mes:Header><mes:Prepared>2026-09-11T12:00:00Z</mes:Prepared></mes:Header>
 <mes:Structures>
  <str:Dataflows><str:Dataflow agencyID="TEST" id="DF_PRICES" version="2.0"
    isFinal="true" isExternalReference="false">
   <com:Name xml:lang="en">Consumer prices</com:Name>
   <str:Structure><Ref agencyID="TEST" id="DSD_PRICES" version="1.0"
     class="DataStructure" package="datastructure"/></str:Structure>
  </str:Dataflow></str:Dataflows>
  <str:DataStructures><str:DataStructure agencyID="TEST" id="DSD_PRICES" version="1.0">
   <com:Name xml:lang="en">Price structure</com:Name>
   <str:DataStructureComponents><str:DimensionList>
    <str:Dimension id="REF_AREA" position="1">
     <str:ConceptIdentity><Ref agencyID="TEST" maintainableParentID="CS"
       maintainableParentVersion="1.0" id="REF_AREA" class="Concept"/></str:ConceptIdentity>
     <str:LocalRepresentation><str:Enumeration><Ref agencyID="TEST" id="CL_AREA"
       version="1.0" class="Codelist"/></str:Enumeration></str:LocalRepresentation>
    </str:Dimension>
    <str:TimeDimension id="TIME_PERIOD" position="2"/>
   </str:DimensionList><str:AttributeList>
    <str:Attribute id="OBS_STATUS">
     <str:LocalRepresentation><str:Enumeration><Ref agencyID="TEST" id="CL_STATUS"
       version="1.0" class="Codelist"/></str:Enumeration></str:LocalRepresentation>
    </str:Attribute>
   </str:AttributeList></str:DataStructureComponents>
  </str:DataStructure></str:DataStructures>
  <str:Concepts><str:ConceptScheme agencyID="TEST" id="CS" version="1.0">
   <str:Concept id="REF_AREA"><com:Name xml:lang="en">Reference area</com:Name></str:Concept>
  </str:ConceptScheme></str:Concepts>
  <str:Codelists>
   <str:Codelist agencyID="TEST" id="CL_AREA" version="1.0">
    <com:Name xml:lang="en">Reference areas</com:Name>
    <str:Code id="CHN"><com:Name xml:lang="en">China</com:Name></str:Code>
    <str:Code id="ZAF"><com:Name xml:lang="en">South Africa</com:Name></str:Code>
    <str:Code id="W00"><com:Name xml:lang="en">World</com:Name></str:Code>
   </str:Codelist>
   <str:Codelist agencyID="TEST" id="CL_STATUS" version="1.0">
    <com:Name xml:lang="en">Observation status</com:Name>
    <str:Code id="A"><com:Name xml:lang="en">Normal value</com:Name></str:Code>
   </str:Codelist>
  </str:Codelists>
 </mes:Structures>
</mes:Structure>
"""

CONSTRAINT_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<mes:Structure xmlns:mes="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
 xmlns:str="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
 xmlns:com="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
 <mes:Structures><str:Constraints>
  <str:ContentConstraint agencyID="TEST" id="DF_PRICES_ACTUAL" version="1.0" type="Actual">
   <str:ConstraintAttachment><str:Dataflow><Ref agencyID="TEST" id="DF_PRICES"
    version="2.0" class="Dataflow"/></str:Dataflow></str:ConstraintAttachment>
   <str:CubeRegion include="true"><com:KeyValue id="REF_AREA">
    <com:Value>CHN</com:Value>
   </com:KeyValue><com:KeyValue id="NEW_CLASS">
    <com:Value>X</com:Value>
   </com:KeyValue><com:KeyValue id="TIME_PERIOD"/></str:CubeRegion>
  </str:ContentConstraint>
 </str:Constraints></mes:Structures>
</mes:Structure>
"""


@pytest.mark.asyncio
async def test_sdmx_harvester_streams_shared_codelists_and_cross_dimension_search(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["references"] == "all"
        return httpx.Response(
            200,
            content=SDMX_FIXTURE,
            headers={"content-type": "application/vnd.sdmx.structure+xml;version=2.1"},
        )

    config = SdmxProviderConfig(
        provider_id="test_sdmx",
        provider_name="Test SDMX",
        base_url="https://example.test/rest",
        catalog_url="https://example.test/catalog",
        dataflow_path="dataflow/all/all/latest",
        dataflow_references="all",
        executable_flows=(("TEST", "DF_PRICES", "PRICES"),),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SdmxCatalogHarvester(config, tmp_path / "raw", client).harvest()

    assert result.snapshot.coverage_status == "partial"
    assert result.snapshot.attributes["dataflow_total"] == 1
    assert result.snapshot.attributes["unique_codelist_total"] == 2
    assert result.snapshot.attributes["unresolved_structure_total"] == 0
    assert result.snapshot.attributes["unresolved_codelist_total"] == 0
    dataset = result.snapshot.datasets[0]
    assert dataset.dataset_id == "TEST:DF_PRICES"
    assert dataset.executable is True
    assert [item.component_kind for item in dataset.dimensions] == [
        "dimension",
        "time",
        "attribute",
    ]

    repository = SourceIndexRepository(tmp_path / "source-index.sqlite3")
    repository.replace_provider_with_codelists(result.snapshot, result.codelists())

    assert repository.search("China prices")[0].dataset_id == "TEST:DF_PRICES"
    values = repository.dimension_values("test_sdmx", "TEST:DF_PRICES", "REF_AREA")
    assert values["total"] == 3
    assert [item["code"] for item in values["values"]] == ["CHN", "W00", "ZAF"]
    assert next(item for item in values["values"] if item["code"] == "W00")[
        "is_aggregate"
    ] is True
    assert next(item for item in values["values"] if item["code"] == "ZAF")[
        "is_aggregate"
    ] is None
    assert repository.provider_summaries()[0]["dimension_value_count"] == 4


@pytest.mark.asyncio
async def test_sdmx_harvester_applies_actual_availability_and_geo_classification(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            CONSTRAINT_FIXTURE
            if "contentconstraint" in request.url.path
            else SDMX_FIXTURE
        )
        return httpx.Response(
            200,
            content=content,
            headers={"content-type": "application/vnd.sdmx.structure+xml;version=2.1"},
        )

    config = SdmxProviderConfig(
        provider_id="test_sdmx_complete",
        provider_name="Test SDMX Complete",
        base_url="https://example.test/rest",
        catalog_url="https://example.test/catalog",
        dataflow_path="dataflow/all/all/latest",
        dataflow_references="all",
        constraint_paths=("contentconstraint/all/all/latest",),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SdmxCatalogHarvester(config, tmp_path / "raw", client).harvest()

    assert result.snapshot.coverage_status == "complete"
    assert result.snapshot.attributes["availability_flow_total"] == 1
    assert result.snapshot.attributes["availability_only_dimension_total"] == 1
    assert result.snapshot.datasets[0].attributes["availability_status"] == "Actual"
    assert result.snapshot.datasets[0].attributes["availability_only_dimensions"] == (
        "NEW_CLASS"
    )

    repository = SourceIndexRepository(tmp_path / "source-index.sqlite3")
    repository.replace_provider_with_codelists(result.snapshot, result.codelists())
    values = repository.dimension_values(
        "test_sdmx_complete", "TEST:DF_PRICES", "REF_AREA"
    )
    assert values["total"] == 1
    assert values["values"][0]["code"] == "CHN"
    assert values["values"][0]["is_aggregate"] is None
    new_values = repository.dimension_values(
        "test_sdmx_complete", "TEST:DF_PRICES", "NEW_CLASS"
    )
    assert new_values["values"] == [
        {
            "code": "X",
            "label": "X",
            "description": None,
            "is_aggregate": None,
            "parent_codes": [],
            "attributes": {"catalog_status": "availability_only"},
        }
    ]


@pytest.mark.asyncio
async def test_sdmx_harvester_resumes_provider_not_advertised_availability(
    tmp_path: Path,
) -> None:
    availability_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal availability_calls
        if "availableconstraint" in request.url.path:
            availability_calls += 1
            return httpx.Response(404, headers={"content-type": "application/xml"})
        return httpx.Response(
            200,
            content=SDMX_FIXTURE,
            headers={"content-type": "application/vnd.sdmx.structure+xml;version=2.1"},
        )

    config = SdmxProviderConfig(
        provider_id="test_sdmx_unadvertised",
        provider_name="Test SDMX Unadvertised",
        base_url="https://example.test/rest",
        catalog_url="https://example.test/catalog",
        dataflow_path="dataflow/all/all/latest",
        dataflow_references="all",
        availability_path_template=(
            "availableconstraint/{agency},{flow},{version}/all/all/all"
        ),
        allow_unadvertised_availability=True,
        availability_request_interval_seconds=0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await SdmxCatalogHarvester(config, tmp_path / "raw", client).harvest()
        second = await SdmxCatalogHarvester(config, tmp_path / "raw", client).harvest()

    assert availability_calls == 1
    assert first.snapshot.coverage_status == "complete"
    assert first.snapshot.attributes["unadvertised_availability_flow_total"] == 1
    assert first.snapshot.source_sha256 == second.snapshot.source_sha256
