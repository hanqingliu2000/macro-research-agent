from __future__ import annotations

from pydantic import BaseModel


class MembershipRecord(BaseModel):
    code: str
    effective_from: str
    effective_to: str | None = None


class ControlledGeography(BaseModel):
    geography_id: str
    canonical_label: str
    kind: str
    aliases: list[str]
    members: list[MembershipRecord]
    source: str
    registry_version: str


class GeographyNotFound(LookupError):
    pass


class ControlledGeographyResolver:
    version = "mra-geography-v1"

    def __init__(self) -> None:
        country_codes = {
            "China": "CHN",
            "United States": "USA",
            "Japan": "JPN",
            "Germany": "DEU",
            "France": "FRA",
            "Italy": "ITA",
            "Canada": "CAN",
            "United Kingdom": "GBR",
        }
        self._records = [
            ControlledGeography(
                geography_id=f"country-{code.lower()}",
                canonical_label=label,
                kind="country",
                aliases=[label.lower(), code.lower()],
                members=[MembershipRecord(code=code, effective_from="1900")],
                source="ISO 3166-1 alpha-3 controlled snapshot",
                registry_version=self.version,
            )
            for label, code in country_codes.items()
        ]
        groups = {
            "G7": ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"],
            "Euro area": [
                "AUT",
                "BEL",
                "HRV",
                "CYP",
                "EST",
                "FIN",
                "FRA",
                "DEU",
                "GRC",
                "IRL",
                "ITA",
                "LVA",
                "LTU",
                "LUX",
                "MLT",
                "NLD",
                "PRT",
                "SVK",
                "SVN",
                "ESP",
            ],
        }
        for label, codes in groups.items():
            self._records.append(
                ControlledGeography(
                    geography_id=f"group-{label.lower().replace(' ', '-')}",
                    canonical_label=label,
                    kind="country_group",
                    aliases=[
                        label.lower(),
                        "eurozone" if label == "Euro area" else "group of seven",
                    ],
                    members=[MembershipRecord(code=code, effective_from="2023") for code in codes],
                    source=f"MRA versioned {label} membership snapshot",
                    registry_version=self.version,
                )
            )

    def resolve(self, intent: str) -> ControlledGeography:
        normalized = intent.strip().lower()
        for record in self._records:
            if normalized == record.canonical_label.lower() or normalized in record.aliases:
                return record
        raise GeographyNotFound(intent)
