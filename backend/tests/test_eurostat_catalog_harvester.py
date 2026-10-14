from __future__ import annotations

import gzip
from pathlib import Path

import httpx
import pytest
from macro_research_agent.knowledge.harvest.eurostat import EurostatCatalogHarvester
from macro_research_agent.knowledge.source_index import SourceIndexRepository


def codelists_xml(items: list[tuple[str, str, list[tuple[str, str]]]]) -> bytes:
    codelists = "".join(
        f'<s:Codelist agencyID="ESTAT" id="{item_id}" version="{version}">'
        f'<c:Name xml:lang="en">{item_id}</c:Name>'
        + "".join(
            f'<s:Code id="{code}"><c:Name xml:lang="en">{label}</c:Name></s:Code>'
            for code, label in values
        )
        + "</s:Codelist>"
        for item_id, version, values in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message" '
        'xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure" '
        'xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">'
        f"<m:Structures><s:Codelists>{codelists}</s:Codelists></m:Structures>"
        "</m:Structure>"
    ).encode()


@pytest.mark.asyncio
async def test_eurostat_catalog_harvester_merges_main_and_comext(
    tmp_path: Path,
) -> None:
    toc = b"""<?xml version="1.0" encoding="UTF-8"?>
    <nt:tree xmlns:nt="urn:eu.europa.ec.eurostat.navtree" creationDate="20260911T2100">
      <nt:leaf type="dataset">
        <nt:title language="en">HICP - monthly data</nt:title>
        <nt:code>prc_hicp_minr</nt:code>
        <nt:lastUpdate>11.09.2026</nt:lastUpdate>
        <nt:dataStart>1996-M01</nt:dataStart><nt:dataEnd>2026-M08</nt:dataEnd>
        <nt:values>2</nt:values>
        <nt:shortDescription language="en">Harmonised consumer prices.</nt:shortDescription>
        <nt:metadata format="html">https://example.test/hicp-metadata</nt:metadata>
      </nt:leaf>
    </nt:tree>"""
    metabase = gzip.compress(
        b"prc_hicp_minr\tcoicop18\tTOTAL\n"
        b"prc_hicp_minr\tgeo\tEU27_2020\n"
        b"prc_hicp_minr\tgeo\tDE\n"
        b"prc_hicp_minr\tgeo\tZA\n"
        b"prc_hicp_minr\ttime\t2026-M08\n"
        b"prc_hicp_minr\tunit\tI25\n"
    )
    main_codelists = gzip.compress(
        codelists_xml(
            [
                ("COICOP18", "1.0", [("TOTAL", "All-items HICP")]),
                (
                    "GEO",
                    "1.0",
                    [
                        ("EU27_2020", "European Union - 27 countries"),
                        ("DE", "Germany"),
                        ("ZA", "South Africa"),
                    ],
                ),
                ("TIME", "1.0", [("2026-M08", "August 2026")]),
                ("UNIT", "1.0", [("I25", "Index, 2025=100")]),
            ]
        )
    )
    dataflows = b"""<?xml version="1.0"?>
    <m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
      xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
      xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
      <m:Header><m:Prepared>2026-09-11T21:00:00Z</m:Prepared></m:Header>
      <m:Structures><s:Dataflows><s:Dataflow agencyID="ESTAT" id="DS-1" version="1.0">
        <c:Name xml:lang="en">Comext trade</c:Name><s:Structure>
          <Ref agencyID="ESTAT" id="DS-1" version="1.0" class="DataStructure"/>
        </s:Structure>
      </s:Dataflow></s:Dataflows></m:Structures>
    </m:Structure>"""
    structures = b"""<?xml version="1.0"?>
    <m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
      xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
      xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
      <m:Structures><s:DataStructures><s:DataStructure agencyID="ESTAT" id="DS-1" version="1.0">
        <s:DataStructureComponents><s:DimensionList>
          <s:Dimension id="freq" position="1"><s:LocalRepresentation><s:Enumeration>
            <Ref agencyID="ESTAT" id="CXT_FREQ" version="1.0" class="Codelist"/>
          </s:Enumeration></s:LocalRepresentation></s:Dimension>
          <s:Dimension id="reporter" position="2"><s:LocalRepresentation><s:Enumeration>
            <Ref agencyID="ESTAT" id="CXT_FREE_ISO" version="1.0" class="Codelist"/>
          </s:Enumeration></s:LocalRepresentation></s:Dimension>
          <s:TimeDimension id="TIME_PERIOD" position="3"/>
        </s:DimensionList><s:MeasureList><s:PrimaryMeasure id="OBS_VALUE"/></s:MeasureList>
        </s:DataStructureComponents>
      </s:DataStructure></s:DataStructures></m:Structures>
    </m:Structure>"""
    comext_codelists = codelists_xml(
        [
            ("CXT_FREQ", "1.0", [("A", "Annual")]),
            (
                "CXT_FREE_ISO",
                "1.0",
                [("WORLD", "World"), ("DE", "Germany")],
            ),
        ]
    )
    constraint = b"""<?xml version="1.0"?>
    <m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
      xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
      xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
      <m:Structures><s:Constraints><s:ContentConstraint agencyID="ESTAT" id="DS-1" version="1.0">
        <s:ConstraintAttachment><s:Dataflow><Ref agencyID="ESTAT" id="DS-1"
          version="1.0" class="Dataflow"/></s:Dataflow></s:ConstraintAttachment>
        <s:CubeRegion include="true">
          <c:KeyValue id="freq"><c:Value>A</c:Value></c:KeyValue>
          <c:KeyValue id="reporter"><c:Value>WORLD</c:Value><c:Value>DE</c:Value></c:KeyValue>
          <c:KeyValue id="TIME_PERIOD"><c:Value>2025</c:Value></c:KeyValue>
        </s:CubeRegion>
      </s:ContentConstraint></s:Constraints></m:Structures>
    </m:Structure>"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/catalogue/toc/xml"):
            content = toc
        elif path.endswith("/catalogue/metabase.txt.gz"):
            content = metabase
        elif "/sdmx/3.0/structure/codelist/" in path:
            content = main_codelists
        elif path.endswith("/sdmx/2.1/dataflow/ESTAT/all"):
            content = dataflows
        elif path.endswith("/sdmx/2.1/datastructure/all/all/latest"):
            content = structures
        elif path.endswith("/sdmx/2.1/codelist/all/all/latest"):
            content = comext_codelists
        elif path.endswith("/sdmx/2.1/contentconstraint/ESTAT/DS-1/latest"):
            content = constraint
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await EurostatCatalogHarvester(
            tmp_path / "raw", client, request_interval_seconds=0
        ).harvest()

    assert result.snapshot.coverage_status == "complete"
    assert result.snapshot.attributes["main_dataset_total"] == 1
    assert result.snapshot.attributes["comext_prodcom_dataset_total"] == 1
    assert len(result.snapshot.datasets) == 2

    repository = SourceIndexRepository(tmp_path / "source-index.sqlite3")
    repository.replace_provider_with_codelists(result.snapshot, result.codelists())
    main_geos = repository.dimension_values("eurostat", "ESTAT:prc_hicp_minr", "geo")
    assert main_geos["total"] == 3
    eu = next(item for item in main_geos["values"] if item["code"] == "EU27_2020")
    de = next(item for item in main_geos["values"] if item["code"] == "DE")
    za = next(item for item in main_geos["values"] if item["code"] == "ZA")
    assert eu["is_aggregate"] is True
    assert de["is_aggregate"] is False
    assert za["is_aggregate"] is False
    reporters = repository.dimension_values("eurostat", "ESTAT:DS-1", "reporter")
    assert reporters["total"] == 2
    matches = repository.search("Harmonised consumer prices", provider_id="eurostat")
    assert matches[0].dataset_id == "ESTAT:prc_hicp_minr"
