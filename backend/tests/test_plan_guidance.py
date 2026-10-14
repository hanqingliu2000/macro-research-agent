from macro_research_agent.workflow.plan_guidance import normalize_plan_guidance


def test_non_blocking_discovery_plumbing_is_not_a_plan_blocker_or_caution() -> None:
    blockers, cautions = normalize_plan_guidance(
        [
            "Confirm whether a future connector admission should be pursued for the discovery-only "
            "IMF IIP datasets; this does not block the executable WEO-based plan."
        ],
        [
            "The discovery index is a low-frequency bounded retrieval and cannot prove current "
            "IMF availability.",
            "The IMF IIP dataset appeared as executable=false and is discovery-only.",
            "SDMX WEO vintages can revise historical debt figures.",
        ],
    )

    assert blockers == []
    assert cautions == ["SDMX WEO vintages can revise historical debt figures."]


def test_material_non_blocking_note_becomes_a_caution_and_real_blocker_remains() -> None:
    blockers, cautions = normalize_plan_guidance(
        [
            "Confirm the requested debt definition before acquisition.",
            "The short history may reduce forecast stability; this is non-blocking.",
        ],
        [],
    )

    assert blockers == ["Confirm the requested debt definition before acquisition."]
    assert cautions == ["The short history may reduce forecast stability; this is non-blocking."]


def test_observation_availability_claims_wait_for_acquisition() -> None:
    blockers, cautions = normalize_plan_guidance(
        [
            "IMF WEO has no reported values for 2018-2020.",
            "IMF Data is planned but unavailable; attach a local file or enable an executable "
            "connector.",
        ],
        [
            "Exact codes must be validated at acquisition.",
            "WEO vintages can revise historical debt figures.",
        ],
    )

    assert blockers == [
        "IMF Data is planned but unavailable; attach a local file or enable an executable "
        "connector."
    ]
    assert cautions == ["WEO vintages can revise historical debt figures."]
